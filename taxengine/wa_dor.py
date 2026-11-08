"""Washington rates by street address, from the Department of Revenue (DOR).

A ZIP code can cross city lines, so a rate picked by the ZIP alone is sometimes
the wrong city's. For example, 98004 is Bellevue (10.3%) but the ZIP5 table
gives Seattle's 10.55%. DOR assigns every address a location code with its own
rate, and offers two ways to find it:

- The address lookup web service: send the street, city and ZIP, get back the
  location code and rate. Always current, but needs the network.
  https://dor.wa.gov/wa-sales-tax-rate-lookup-url-interface

- The quarterly ZIP+4 file: maps each ZIP+4 range to a location code. Works
  offline, but only when the address has a 9-digit ZIP.
  https://dor.wa.gov/taxes-rates/sales-use-tax-rates/downloadable-database

WashingtonResolver tries those in order. When neither gives an answer, it
returns None and the engine falls back to the ZIP5 table.
"""

import csv
import logging
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .core import Address, RateRow, normalize_zip  # noqa: F401  (Address re-exported)

# Drop DOR's quarterly files here (unzipped): a Rates*.csv and/or a Zip4*.csv.
DEFAULT_DOR_DIR = Path(__file__).resolve().parent.parent / "data" / "wa-dor"

log = logging.getLogger(__name__)

LOOKUP_URL = "https://webgis.dor.wa.gov/webapi/AddressRates.aspx"

# DOR result codes that point at one location: 0-4 mean the address or its
# ZIP+4 was found. 5 means only the 5-digit ZIP matched, which is the case
# we are trying to avoid, so it falls through to the next source.
FOUND_CODES = {"0", "1", "2", "3", "4"}


@dataclass(frozen=True)
class Location:
    code: str
    name: str
    state_rate: Decimal
    local_rate: Decimal
    rate: Decimal


def _cols(rec):
    """Row keys upper-cased and stripped, so small header changes don't matter."""
    return {k.strip().upper(): (v or "").strip() for k, v in rec.items() if k}


def load_location_rates(path):
    """Read DOR's Rates file (from Rates_YYQn.zip) into {code: Location}.

    Columns: NAME, CODE, STATE, LOCAL, RTA, RATE, EFFECTIVE DATE, EXPIRATION DATE.
    LOCAL already includes any RTA rate, so RATE = STATE + LOCAL.
    """
    out = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for rec in csv.DictReader(f):
            rec = _cols(rec)
            code = rec["CODE"].zfill(4)
            out[code] = Location(code, rec["NAME"], Decimal(rec["STATE"]), Decimal(rec["LOCAL"]), Decimal(rec["RATE"]))
    return out


def split_zip(zip_code):
    """'98004-1234' or '980041234' -> ('98004', '1234'); '98004' -> ('98004', None)."""
    digits = "".join(c for c in str(zip_code) if c.isdigit())
    if len(digits) == 9:
        return digits[:5], digits[5:]
    return normalize_zip(zip_code), None


class Zip4Table:
    """DOR's ZIP+4 short file (from Zip4QnYYC.zip).

    Columns: ZIP, PLUS4_LOW, PLUS4_HIGH, CODE, STATE, LOCAL, TOT_RATE, EFF_START, EFF_END.
    """

    def __init__(self, ranges):
        self.ranges = ranges    # {zip5: [(low, high, Location), ...]}

    @classmethod
    def load(cls, path):
        ranges = {}
        with open(path, newline="", encoding="utf-8-sig") as f:
            for rec in csv.DictReader(f):
                rec = _cols(rec)
                loc = Location(rec["CODE"].zfill(4), "", Decimal(rec["STATE"]),
                               Decimal(rec["LOCAL"]), Decimal(rec["TOT_RATE"]))
                ranges.setdefault(rec["ZIP"].zfill(5), []).append(
                    (rec["PLUS4_LOW"].zfill(4), rec["PLUS4_HIGH"].zfill(4), loc))
        return cls(ranges)

    def find(self, zip_code):
        """The Location for a 9-digit ZIP, or for a 5-digit ZIP that sits in one location only."""
        zip5, plus4 = split_zip(zip_code)
        ranges = self.ranges.get(zip5, [])
        if plus4:
            for low, high, loc in ranges:
                if low <= plus4 <= high:
                    return loc
            return None
        codes = {loc.code for _, _, loc in ranges}
        return ranges[0][2] if len(codes) == 1 else None

    def is_split(self, zip5):
        """True when a 5-digit ZIP covers more than one location code."""
        return len({loc.code for _, _, loc in self.ranges.get(zip5, [])}) > 1


def _fetch(url, timeout):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


class DorAddressLookup:
    """Calls DOR's address rate lookup. Answers are cached per address.

    fetch(url, timeout) -> response text; replace it in tests to avoid the network.
    """

    def __init__(self, fetch=_fetch, timeout=5):
        self.fetch = fetch
        self.timeout = timeout
        self.cache = {}

    def find(self, address):
        key = (address.line1.strip().upper(), address.city.strip().upper(), address.zip_code.strip())
        if key not in self.cache:
            self.cache[key] = self._ask(address)
        return self.cache[key]

    def _ask(self, address):
        query = urllib.parse.urlencode({
            "output": "text", "addr": address.line1, "city": address.city, "zip": address.zip_code,
        })
        try:
            text = self.fetch(f"{LOOKUP_URL}?{query}", self.timeout)
        except OSError as e:
            log.warning("WA DOR address lookup failed (%s); using the next rate source", e)
            return None     # network trouble: fall back to the next source
        # The answer looks like: LocationCode=3406 Rate=0.084 ResultCode=0
        fields = dict(part.split("=", 1) for part in text.split() if "=" in part)
        if fields.get("ResultCode") not in FOUND_CODES or not fields.get("LocationCode"):
            log.warning("WA DOR could not place %r, %r %r (result code %s); using the next rate source",
                        address.line1, address.city, address.zip_code, fields.get("ResultCode"))
            return None
        rate = Decimal(fields["Rate"])
        state_rate = Decimal("0.065")
        return Location(fields["LocationCode"].zfill(4), "", state_rate, rate - state_rate, rate)


class WashingtonResolver:
    """Finds the DOR location for a Washington address.

    Order: ZIP+4 file (when the ZIP has 9 digits), then the DOR web lookup (when
    there is a street), then the ZIP+4 file for a ZIP5 that sits in one
    location only. Returns a RateRow, or None to use the ZIP5 table.

    names: optional {code: Location} from load_location_rates(), for readable
    location names such as "Bellevue" instead of "WA location 1704".
    """

    def __init__(self, zip4=None, lookup=None, names=None):
        self.zip4 = zip4
        self.lookup = lookup
        self.names = names or {}

    @classmethod
    def from_files(cls, folder=DEFAULT_DOR_DIR, use_web_lookup=False):
        """Load whichever DOR files are in folder: a Rates*.csv and/or a Zip4*.csv."""
        folder = Path(folder)
        rates = sorted(folder.glob("Rates*.csv"))
        zips = sorted(folder.glob("Zip4*.csv"))
        return cls(
            zip4=Zip4Table.load(zips[-1]) if zips else None,
            lookup=DorAddressLookup() if use_web_lookup else None,
            names=load_location_rates(rates[-1]) if rates else None,
        )

    def resolve(self, address):
        zip5, plus4 = split_zip(address.zip_code)
        loc, source = None, ""
        if self.zip4 and plus4:
            loc, source = self.zip4.find(address.zip_code), "dor-zip4"
        if not loc and self.lookup and address.line1.strip():
            loc, source = self.lookup.find(address), "dor-address"
        if not loc and self.zip4 and not plus4:
            loc, source = self.zip4.find(zip5), "dor-zip4"
        if not loc:
            return None
        known = self.names.get(loc.code)
        name = known.name if known and known.name else f"WA location {loc.code}"
        return RateRow(
            state="WA",
            zip_code=zip5,
            region=f"{name} ({loc.code})",
            combined=loc.rate,
            state_rate=loc.state_rate,
            county_rate=Decimal(0),
            city_rate=loc.rate - loc.state_rate,   # DOR gives one local rate for city + county + transit
            special_rate=Decimal(0),
            source=source,
        )
