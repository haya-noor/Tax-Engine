"""Stripe adapter tests, using a fake Stripe client (no network, no stripe package)."""

import unittest
from decimal import Decimal
from pathlib import Path

from adapters.stripe_invoices import NoTaxAddressError, add_tax_to_invoice, tax_amounts_for
from taxengine import TaxEngine

FIXTURES = Path(__file__).parent / "fixtures" / "rates"


class FakePage(list):
    def auto_paging_iter(self):
        return iter(self)


class FakeStripe:
    """Just enough of stripe.StripeClient().v1.invoices for the adapter."""

    def __init__(self, invoice, lines):
        self.invoice, self.lines, self.updates = invoice, lines, {}
        self.v1 = self
        self.invoices = self
        self.line_items = self

    def retrieve(self, invoice_id):
        return self.invoice

    def list(self, invoice_id, params):
        return FakePage(self.lines)

    def update(self, invoice_id, line_id, params):
        self.updates[line_id] = params["tax_amounts"]


def chicago_invoice(**changes):
    invoice = {"id": "in_1", "status": "draft", "customer_shipping": None,
               "customer_address": {"postal_code": "60601", "state": "IL", "country": "US"}}
    invoice.update(changes)
    return invoice


class StripeAdapterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = TaxEngine(FIXTURES)

    def test_one_tax_amount_per_layer_adding_up_to_the_total(self):
        result = self.engine.calculate("60601", "59.99")
        amounts = tax_amounts_for(result)
        self.assertEqual([a["tax_rate_data"]["jurisdiction_level"] for a in amounts],
                         ["state", "county", "city", "district"])
        self.assertEqual(sum(a["amount"] for a in amounts), 630)   # 59.99 x 10.5% = 6.30
        self.assertEqual(amounts[0]["taxable_amount"], 5999)
        self.assertEqual(amounts[0]["tax_rate_data"]["percentage"], 6.25)

    def test_layers_rounding_is_balanced(self):
        result = self.engine.calculate("60601", "1.00")
        self.assertEqual(result.total_tax, Decimal("0.11"))                 # 1.00 x 10.5% = 0.105
        self.assertEqual(sum(l.tax for l in result.layers), Decimal("0.10"))  # layers round to 0.06+0.02+0.01+0.01
        self.assertEqual(sum(l.tax for l in result.balanced_layers()), Decimal("0.11"))

    def test_sets_tax_on_each_line_after_discounts(self):
        lines = [{"id": "il_1", "amount": 10000, "discount_amounts": [{"amount": 2000}]},
                 {"id": "il_2", "amount": 5000, "discount_amounts": []},
                 {"id": "il_3", "amount": -500}]
        fake = FakeStripe(chicago_invoice(), lines)
        total = add_tax_to_invoice(fake, self.engine, "in_1")
        self.assertEqual(sum(a["amount"] for a in fake.updates["il_1"]), 840)   # 80.00 x 10.5%
        self.assertEqual(sum(a["amount"] for a in fake.updates["il_2"]), 525)
        self.assertNotIn("il_3", fake.updates)
        self.assertEqual(total, 1365)

    def test_shipping_address_wins_over_billing(self):
        invoice = chicago_invoice(customer_shipping={"address": {"postal_code": "02108", "state": "MA", "country": "US"}})
        fake = FakeStripe(invoice, [{"id": "il_1", "amount": 5000}])
        self.assertEqual(add_tax_to_invoice(fake, self.engine, "in_1"), 313)

    def test_states_we_dont_collect_in_get_no_tax(self):
        engine = TaxEngine(FIXTURES, collect_in={"MA"})
        fake = FakeStripe(chicago_invoice(), [{"id": "il_1", "amount": 5000}])
        self.assertEqual(add_tax_to_invoice(fake, engine, "in_1"), 0)
        self.assertEqual(fake.updates, {})

    def test_refuses_finalized_invoices_and_missing_addresses(self):
        with self.assertRaises(ValueError):
            add_tax_to_invoice(FakeStripe(chicago_invoice(status="open"), []), self.engine, "in_1")
        with self.assertRaises(NoTaxAddressError):
            add_tax_to_invoice(FakeStripe(chicago_invoice(customer_address=None), []), self.engine, "in_1")


if __name__ == "__main__":
    unittest.main()
