"""Checks against the real rate tables in data/. Skipped if they are not there."""

import unittest
from decimal import Decimal

from taxengine import DEFAULT_RATES_DIR, TaxEngine

HAVE_DATA = any(DEFAULT_RATES_DIR.glob("TAXRATES_ZIP5_*.csv"))


@unittest.skipUnless(HAVE_DATA, f"no rate tables in {DEFAULT_RATES_DIR}")
class RateDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = TaxEngine()

    def test_every_state_file_loads(self):
        states = {r.state for rows in self.engine.rates.values() for r in rows}
        self.assertEqual(len(states), 52)  # 50 states + DC + PR

    def test_known_rates(self):
        self.assertEqual(self.engine.calculate("60601", "100").total_tax, Decimal("10.50"))
        self.assertEqual(self.engine.calculate("02108", "50").total_tax, Decimal("3.13"))

    def test_combined_matches_layers_within_rounding(self):
        for rows in self.engine.rates.values():
            for r in rows:
                layers = r.state_rate + r.county_rate + r.city_rate + r.special_rate
                self.assertLessEqual(abs(layers - r.combined), Decimal("0.000001"), r)


if __name__ == "__main__":
    unittest.main()
