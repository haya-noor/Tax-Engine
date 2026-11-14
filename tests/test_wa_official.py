"""Check Washington results against official Department of Revenue figures.

Sources are listed in tests/fixtures/validation/README.md.
"""

import csv
import unittest
from decimal import Decimal
from pathlib import Path

from taxengine import DEFAULT_RATES_DIR, TaxEngine, money

VALIDATION = Path(__file__).resolve().parent / "fixtures" / "validation"
HAVE_WA = any(DEFAULT_RATES_DIR.glob("TAXRATES_ZIP5_WA*.csv"))

# Rows copied from DOR's Retail Sales Tax Collection Schedules:
# (lowest price, highest price, tax due for any price in that range).
SCHEDULE_10_0 = [
    ("0.05", "0.14", "0.01"),
    ("99.95", "100.04", "10.00"),
]
SCHEDULE_8_9 = [
    ("0.06", "0.16", "0.01"),
    ("0.17", "0.28", "0.02"),
    ("1.07", "1.17", "0.10"),
]


def prices(low, high):
    """Every whole-cent price from low to high."""
    cent = Decimal("0.01")
    p = Decimal(low)
    while p <= Decimal(high):
        yield p
        p += cent


class CollectionScheduleTest(unittest.TestCase):
    """Rounding: our tax for each price matches DOR's printed schedule."""

    def check(self, rate, schedule):
        for low, high, tax in schedule:
            for price in prices(low, high):
                self.assertEqual(money(price * Decimal(rate)), Decimal(tax), price)

    def test_10_percent(self):
        self.check("0.100", SCHEDULE_10_0)

    def test_8_9_percent(self):
        self.check("0.089", SCHEDULE_8_9)

    def test_just_below_first_band_is_zero(self):
        self.assertEqual(money(Decimal("0.04") * Decimal("0.100")), Decimal("0.00"))
        self.assertEqual(money(Decimal("0.05") * Decimal("0.089")), Decimal("0.00"))


@unittest.skipUnless(HAVE_WA, "no WA rate table in data/")
class DorRateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = TaxEngine(collect_in=["WA"])
        with open(VALIDATION / "wa_dor_rates_2026q4.csv", newline="") as f:
            cls.rows = list(csv.DictReader(f))

    def test_city_rates_match_dor(self):
        self.assertGreaterEqual(len(self.rows), 30)
        for row in self.rows:
            with self.subTest(city=row["city"]):
                rate = self.engine.find_rate(row["zip"], "WA").combined
                self.assertEqual(rate, Decimal(row["dor_rate"]))

    def test_engine_matches_schedules_end_to_end(self):
        # Olympia is 10.0% and Vancouver is 8.9% in DOR's Q4 2026 table.
        for zip_code, schedule in (("98501", SCHEDULE_10_0), ("98660", SCHEDULE_8_9)):
            for low, high, tax in schedule:
                for price in prices(low, high):
                    result = self.engine.calculate(zip_code, price, "WA")
                    self.assertEqual(result.total_tax, Decimal(tax), (zip_code, price))


if __name__ == "__main__":
    unittest.main()
