import unittest
from decimal import Decimal
from pathlib import Path

from taxengine import AmbiguousZipError, TaxEngine, UnknownZipError, money, normalize_zip

FIXTURES = Path(__file__).parent / "fixtures" / "rates"


class CoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = TaxEngine(FIXTURES)

    def test_layers_and_total(self):
        result = self.engine.calculate("60601", "100")
        self.assertEqual(result.state, "IL")
        self.assertEqual(result.combined_rate, Decimal("0.105"))
        self.assertEqual(result.total_tax, Decimal("10.50"))
        self.assertEqual([l.tax for l in result.layers],
                         [Decimal("6.25"), Decimal("1.75"), Decimal("1.25"), Decimal("1.25")])

    def test_records_rate_version(self):
        self.assertEqual(self.engine.calculate("60601", "1").rate_version, "rates")

    def test_rounds_half_up_to_the_cent(self):
        self.assertEqual(money(Decimal("50") * Decimal("0.0625")), Decimal("3.13"))
        self.assertEqual(self.engine.calculate("02108", "50").total_tax, Decimal("3.13"))

    def test_zip_normalization(self):
        self.assertEqual(normalize_zip(" 2108 "), "02108")
        self.assertEqual(normalize_zip("02108-1234"), "02108")
        with self.assertRaises(ValueError):
            normalize_zip("ABCDE")

    def test_cross_state_zip_needs_state(self):
        with self.assertRaises(AmbiguousZipError):
            self.engine.calculate("88240", "100")
        self.assertEqual(self.engine.calculate("88240", "100", state="TX").total_tax, Decimal("6.25"))
        self.assertEqual(self.engine.calculate("88240", "100", state="nm").total_tax, Decimal("6.56"))

    def test_unknown_zip(self):
        with self.assertRaises(UnknownZipError):
            self.engine.calculate("99999", "10")
        with self.assertRaises(UnknownZipError):
            self.engine.calculate("60601", "10", state="TX")


class OneStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = TaxEngine(FIXTURES, collect_in={"il"})

    def test_only_loads_that_state(self):
        self.assertEqual({r.state for rows in self.engine.rates.values() for r in rows}, {"IL"})

    def test_taxes_the_state_we_collect_in(self):
        self.assertEqual(self.engine.calculate("61801", "200", state="IL").total_tax, Decimal("18.00"))

    def test_other_states_get_zero_tax(self):
        result = self.engine.calculate("88240", "100", state="TX")
        self.assertEqual(result.total_tax, Decimal("0.00"))
        self.assertEqual(result.layers, [])


if __name__ == "__main__":
    unittest.main()
