"""Step 1: the core of the tax engine.

Given a US ZIP code and an amount, return the state, county, city and
special-district rates, the combined rate, and the tax.

Rates come from the client's Avalara ZIP5 rate tables (one CSV per state).
No platform code lives here. Checkout or billing systems connect through
adapters outside this package that call TaxEngine.calculate().
"""

import csv
import os
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

CENT = Decimal("0.01")

# Default data folder: <repo>/data/avalara-2026-10, or set TAXENGINE_RATES_DIR.
DEFAULT_RATES_DIR = Path(
    os.environ.get(
        "TAXENGINE_RATES_DIR",
        Path(__file__).resolve().parent.parent / "data" / "avalara-2026-10",
    )
)


class UnknownZipError(LookupError):
    """The ZIP code is not in the rate tables."""


class AmbiguousZipError(LookupError):
    """The ZIP code exists in more than one state; pass state= to choose."""


@dataclass(frozen=True)
class RateRow:
    state: str
    zip_code: str
    region: str
    combined: Decimal
    state_rate: Decimal
    county_rate: Decimal
    city_rate: Decimal
    special_rate: Decimal


@dataclass(frozen=True)
class LayerTax:
    layer: str      # "state", "county", "city" or "special"
    rate: Decimal
    tax: Decimal


@dataclass(frozen=True)
class TaxResult:
    zip_code: str
    state: str
    region: str
    amount: Decimal
    combined_rate: Decimal
    total_tax: Decimal
    layers: list
    rate_version: str = ""    # the rate table folder used, e.g. "avalara-2026-10"

    def __str__(self):
        lines = [
            f"ZIP {self.zip_code}  {self.region}, {self.state}",
            f"Amount:        {self.amount:>10}",
        ]
        for layer in self.layers:
            lines.append(f"  {layer.layer:<8} {pct(layer.rate):>9}  {layer.tax:>10}")
        lines.append(f"Combined rate: {pct(self.combined_rate):>9}")
        lines.append(f"Total tax:     {self.total_tax:>10}")
        lines.append(f"Grand total:   {self.amount + self.total_tax:>10}")
        return "\n".join(lines)


def pct(rate):
    return f"{(rate * 100).normalize():f}%"


def money(value):
    """Round to cents, half up (the usual US sales tax rounding)."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def normalize_zip(zip_code):
    """Accept '02108', '02108-1234', ' 2108 ' or 2108 and return '02108'."""
    text = str(zip_code).strip().split("-")[0]
    if not text.isdigit() or len(text) > 5:
        raise ValueError(f"Not a valid US ZIP code: {zip_code!r}")
    return text.zfill(5)


def load_rates(rates_dir, states=None):
    """Read TAXRATES_ZIP5_*.csv files into {zip: [RateRow, ...]}.

    A list, because about 80 ZIPs cross a state line (e.g. 88240 is in NM and TX).
    With states (e.g. {"IL"}), only those states' files are read.
    """
    rates = {}
    files = sorted(Path(rates_dir).glob("TAXRATES_ZIP5_*.csv"))
    if states:
        # File names look like TAXRATES_ZIP5_CA202610.csv: the state follows "ZIP5_".
        files = [f for f in files if f.name[len("TAXRATES_ZIP5_"):][:2] in states]
    if not files:
        raise FileNotFoundError(f"No TAXRATES_ZIP5_*.csv files in {rates_dir}")
    for path in files:
        with open(path, newline="", encoding="utf-8") as f:
            for rec in csv.DictReader(f):
                row = RateRow(
                    state=rec["State"],
                    zip_code=rec["ZipCode"].zfill(5),
                    region=rec["TaxRegionName"],
                    combined=Decimal(rec["EstimatedCombinedRate"]),
                    state_rate=Decimal(rec["StateRate"]),
                    county_rate=Decimal(rec["EstimatedCountyRate"]),
                    city_rate=Decimal(rec["EstimatedCityRate"]),
                    special_rate=Decimal(rec["EstimatedSpecialRate"]),
                )
                rates.setdefault(row.zip_code, []).append(row)
    return rates


class TaxEngine:
    """Calculates tax for the states we collect in.

    collect_in: the states the seller is registered in, e.g. {"IL"}. Addresses in
    any other state get 0 tax. None means every state in the rate tables.
    """

    def __init__(self, rates_dir=DEFAULT_RATES_DIR, collect_in=None):
        self.collect_in = {s.upper() for s in collect_in} if collect_in else None
        self.rates = load_rates(rates_dir, self.collect_in)
        self.rate_version = Path(rates_dir).name

    def collects_in(self, state):
        return self.collect_in is None or state.upper() in self.collect_in

    def find_rate(self, zip_code, state=None):
        zip_code = normalize_zip(zip_code)
        rows = self.rates.get(zip_code)
        if not rows:
            raise UnknownZipError(f"ZIP {zip_code} is not in the rate tables")
        if state:
            rows = [r for r in rows if r.state == state.upper()]
            if not rows:
                raise UnknownZipError(f"ZIP {zip_code} is not in {state.upper()}")
        if len(rows) > 1:
            states = ", ".join(r.state for r in rows)
            raise AmbiguousZipError(f"ZIP {zip_code} is in {states}; pass state=")
        return rows[0]

    def calculate(self, zip_code, amount, state=None):
        amount = money(amount)
        if state and not self.collects_in(state):
            return untaxed(normalize_zip(zip_code), state.upper(), amount, self.rate_version)
        row = self.find_rate(zip_code, state)
        layers = [
            LayerTax("state", row.state_rate, money(amount * row.state_rate)),
            LayerTax("county", row.county_rate, money(amount * row.county_rate)),
            LayerTax("city", row.city_rate, money(amount * row.city_rate)),
            LayerTax("special", row.special_rate, money(amount * row.special_rate)),
        ]
        # The total uses the combined rate, so it is never off by a rounded cent
        # from summing the layers. The layers are the breakdown for display.
        return TaxResult(
            zip_code=row.zip_code,
            state=row.state,
            region=row.region,
            amount=amount,
            combined_rate=row.combined,
            total_tax=money(amount * row.combined),
            layers=layers,
            rate_version=self.rate_version,
        )


def untaxed(zip_code, state, amount, rate_version=""):
    """A zero-tax result for a state we don't collect in."""
    return TaxResult(
        zip_code=zip_code,
        state=state,
        region="not collected in this state",
        amount=amount,
        combined_rate=Decimal("0"),
        total_tax=money(0),
        layers=[],
        rate_version=rate_version,
    )
