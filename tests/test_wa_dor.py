"""Washington rates by street address (taxengine.wa_dor). No network: the DOR lookup is faked."""

import unittest
from decimal import Decimal
from pathlib import Path

from adapters.stripe_invoices import add_tax_to_invoice
from taxengine import Address, CartLine, TaxEngine, WashingtonResolver, calculate_cart
from taxengine.wa_dor import DorAddressLookup, Zip4Table, load_location_rates
from tests.test_stripe_adapter import FakeStripe, chicago_invoice

HERE = Path(__file__).parent
RATES = HERE / "fixtures" / "rates"
DOR = HERE / "fixtures" / "wa-dor"
BELLEVUE = Address("450 110th Ave NE", "Bellevue", "WA", "98004")


def fake_dor(answers):
    """A fetch() that answers from {street: response text} and records the URLs."""
    calls = []

    def fetch(url, timeout):
        calls.append(url)
        for street, text in answers.items():
            if street.replace(" ", "+") in url:
                return text
        return "LocationCode=-1 Rate=-1 ResultCode=6"
    fetch.calls = calls
    return fetch


class DorLookupTest(unittest.TestCase):
    def test_found_address(self):
        lookup = DorAddressLookup(fake_dor({"450 110th Ave NE": "LocationCode=1704 Rate=0.103 ResultCode=0"}))
        loc = lookup.find(BELLEVUE)
        self.assertEqual((loc.code, loc.rate, loc.local_rate), ("1704", Decimal("0.103"), Decimal("0.038")))

    def test_answers_are_cached(self):
        fetch = fake_dor({"450 110th Ave NE": "LocationCode=1704 Rate=0.103 ResultCode=0"})
        lookup = DorAddressLookup(fetch)
        lookup.find(BELLEVUE)
        lookup.find(BELLEVUE)
        self.assertEqual(len(fetch.calls), 1)

    def test_zip_only_match_is_not_trusted(self):
        lookup = DorAddressLookup(fake_dor({"450 110th Ave NE": "LocationCode=1726 Rate=0.1055 ResultCode=5"}))
        with self.assertLogs("taxengine.wa_dor", "WARNING"):
            self.assertIsNone(lookup.find(BELLEVUE))

    def test_network_error_falls_through(self):
        def broken(url, timeout):
            raise OSError("no network")
        with self.assertLogs("taxengine.wa_dor", "WARNING"):
            self.assertIsNone(DorAddressLookup(broken).find(BELLEVUE))


class Zip4FileTest(unittest.TestCase):
    def setUp(self):
        self.table = Zip4Table.load(DOR / "Zip4_sample.csv")

    def test_plus4_ranges(self):
        self.assertEqual(self.table.find("98004-1234").code, "1704")
        self.assertEqual(self.table.find("980045500").code, "1708")
        self.assertIsNone(self.table.find("98004-7000"))

    def test_split_zip5_has_no_single_answer(self):
        self.assertTrue(self.table.is_split("98004"))
        self.assertIsNone(self.table.find("98004"))
        self.assertEqual(self.table.find("98101").code, "1726")

    def test_location_names(self):
        self.assertEqual(load_location_rates(DOR / "Rates_sample.csv")["1704"].name, "Bellevue")


class EngineWithAddressTest(unittest.TestCase):
    def engine(self, answers=None, files=True):
        lookup = DorAddressLookup(fake_dor(answers or {}))
        wa = WashingtonResolver.from_files(DOR if files else HERE / "missing")
        wa.lookup = lookup
        return TaxEngine(RATES, resolvers={"WA": wa})

    def test_zip5_alone_overcharges_98004(self):
        self.assertEqual(TaxEngine(RATES).calculate("98004", "100", "WA").total_tax, Decimal("10.55"))

    def test_street_address_gives_bellevue_rate(self):
        engine = self.engine({"450 110th Ave NE": "LocationCode=1704 Rate=0.103 ResultCode=0"})
        result = engine.calculate("98004", "100", "WA", address=BELLEVUE)
        self.assertEqual(result.total_tax, Decimal("10.30"))
        self.assertEqual(result.source, "dor-address")
        self.assertEqual(result.region, "Bellevue (1704)")
        self.assertEqual([(l.layer, l.tax) for l in result.balanced_layers()],
                         [("state", Decimal("6.50")), ("local", Decimal("3.80"))])

    def test_zip_plus4_works_offline(self):
        engine = self.engine()
        result = engine.calculate("98004", "100", "WA", address=Address("", "", "WA", "98004-5500"))
        self.assertEqual((result.total_tax, result.source), (Decimal("10.30"), "dor-zip4"))

    def test_unplaced_address_falls_back_to_zip5(self):
        engine = self.engine(files=False)
        with self.assertLogs("taxengine.wa_dor", "WARNING"):
            result = engine.calculate("98004", "100", "WA", address=BELLEVUE)
        self.assertEqual((result.total_tax, result.source), (Decimal("10.55"), "zip5"))

    def test_other_states_ignore_the_resolver(self):
        engine = self.engine()
        result = engine.calculate("60601", "100", "IL", address=Address("1 Main", "Chicago", "IL", "60601"))
        self.assertEqual(result.total_tax, Decimal("10.50"))

    def test_cart_uses_address(self):
        engine = self.engine({"450 110th Ave NE": "LocationCode=1704 Rate=0.103 ResultCode=0"})
        cart = calculate_cart(engine, "98004", "WA", [CartLine("shirt", "50", category="clothing")],
                              shipping="10", address=BELLEVUE)
        self.assertEqual(cart.total_tax, Decimal("6.18"))     # 60.00 x 10.3%

    def test_stripe_invoice_uses_street(self):
        engine = self.engine({"450 110th Ave NE": "LocationCode=1704 Rate=0.103 ResultCode=0"})
        invoice = chicago_invoice(customer_address={"line1": "450 110th Ave NE", "city": "Bellevue",
                                                    "postal_code": "98004", "state": "WA", "country": "US"})
        fake = FakeStripe(invoice, [{"id": "il_1", "amount": 10000}])
        self.assertEqual(add_tax_to_invoice(fake, engine, "in_1"), 1030)
        levels = [a["tax_rate_data"]["jurisdiction_level"] for a in fake.updates["il_1"]]
        self.assertEqual(levels, ["state", "multiple"])


if __name__ == "__main__":
    unittest.main()
