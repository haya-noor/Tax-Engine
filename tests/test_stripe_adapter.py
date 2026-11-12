"""Stripe adapter tests, using a fake Stripe client (no network, no stripe package)."""

import unittest
from decimal import Decimal
from pathlib import Path

from adapters.stripe_invoices import NoTaxAddressError, add_tax_to_invoice, handle_event, tax_amounts_for
from taxengine import TaxEngine

FIXTURES = Path(__file__).parent / "fixtures" / "rates"


class StripeLike(dict):
    """Behaves like a stripe.StripeObject: item access and to_dict(), but no .get()."""

    def __getattribute__(self, name):
        if name == "get":
            raise AttributeError("'get' is a dict method, but this is not a dict")
        return super().__getattribute__(name)

    def to_dict(self):
        return dict(self)


class FakePage(list):
    def auto_paging_iter(self):
        return iter(self)


class FakeStripe:
    """Just enough of stripe.StripeClient().v1.invoices for the adapter."""

    def __init__(self, invoice, lines):
        self.invoice, self.lines, self.updates = invoice, lines, {}
        self.invoice_item_metadata = {}
        self.v1 = self
        self.invoices = self
        self.line_items = self
        self.invoice_items = self

    def retrieve(self, object_id):
        if object_id.startswith("ii_"):
            return StripeLike({"id": object_id, "metadata": self.invoice_item_metadata.get(object_id, {})})
        return StripeLike(self.invoice)

    def list(self, invoice_id, params):
        return FakePage(StripeLike(line) for line in self.lines)

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


class StripeCategoriesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = TaxEngine(FIXTURES)

    def seattle_invoice(self):
        return chicago_invoice(customer_address={"postal_code": "98101", "state": "WA", "country": "US"})

    def test_categories_and_shipping_from_metadata(self):
        lines = [{"id": "il_shirt", "amount": 4500, "metadata": {"tax_category": "clothing"}},
                 {"id": "il_bread", "amount": 500, "metadata": {"tax_category": "groceries"}},
                 {"id": "il_ship", "amount": 800, "metadata": {"tax_category": "shipping"}}]
        fake = FakeStripe(self.seattle_invoice(), lines)
        total = add_tax_to_invoice(fake, self.engine, "in_1")
        self.assertNotIn("il_bread", fake.updates)                                  # groceries exempt
        self.assertEqual(sum(a["amount"] for a in fake.updates["il_shirt"]), 475)    # 45.00 x 10.55%
        self.assertEqual(sum(a["amount"] for a in fake.updates["il_ship"]), 76)      # 90% of 8.00 x 10.55%
        self.assertEqual(fake.updates["il_ship"][0]["taxable_amount"], 720)
        self.assertEqual(total, 551)

    def test_category_falls_back_to_the_invoice_item(self):
        lines = [{"id": "il_1", "amount": 500, "metadata": {},
                  "parent": {"invoice_item_details": {"invoice_item": "ii_1"}}}]
        fake = FakeStripe(self.seattle_invoice(), lines)
        fake.invoice_item_metadata["ii_1"] = {"tax_category": "groceries"}
        self.assertEqual(add_tax_to_invoice(fake, self.engine, "in_1"), 0)


class WebhookEventTest(unittest.TestCase):
    """What the webhook does with each Stripe event."""

    @classmethod
    def setUpClass(cls):
        cls.engine = TaxEngine(FIXTURES)

    def event(self, type_, obj):
        return {"type": type_, "data": {"object": obj}}

    def test_item_added_to_draft_taxes_the_invoice(self):
        fake = FakeStripe(chicago_invoice(), [{"id": "il_1", "amount": 10000}])
        memo = {}
        note = handle_event(fake, self.engine, self.event("invoiceitem.created", {"id": "ii_1", "invoice": "in_1"}), memo)
        self.assertEqual(sum(a["amount"] for a in fake.updates["il_1"]), 1050)
        self.assertIn("10.50", note)
        # The write triggers another event; the same tax is not written twice.
        fake.updates.clear()
        handle_event(fake, self.engine, self.event("invoiceitem.updated", {"id": "ii_1", "invoice": "in_1"}), memo)
        self.assertEqual(fake.updates, {})

    def test_item_without_invoice_is_ignored(self):
        fake = FakeStripe(chicago_invoice(), [])
        self.assertIsNone(handle_event(fake, self.engine, self.event("invoiceitem.created", {"id": "ii_1", "invoice": None}), {}))

    def test_finalized_invoice_is_left_alone(self):
        fake = FakeStripe(chicago_invoice(status="open"), [{"id": "il_1", "amount": 10000}])
        note = handle_event(fake, self.engine, self.event("invoiceitem.updated", {"id": "ii_1", "invoice": "in_1"}), {})
        self.assertIn("draft", note)
        self.assertEqual(fake.updates, {})

    def test_tax_already_right_is_not_written_again(self):
        # Writing tax makes Stripe send another event; skipping a no-op update stops the loop.
        line = {"id": "il_1", "amount": 10000,
                "taxes": [{"amount": a, "taxable_amount": 10000} for a in (625, 175, 125, 125)]}
        fake = FakeStripe(chicago_invoice(), [line])
        handle_event(fake, self.engine, self.event("invoiceitem.updated", {"id": "ii_1", "invoice": "in_1"}), {})
        self.assertEqual(fake.updates, {})

    def test_tax_no_longer_due_is_removed(self):
        line = {"id": "il_1", "amount": 500, "metadata": {"tax_category": "groceries"},
                "taxes": [{"amount": 53, "taxable_amount": 500}]}
        fake = FakeStripe(chicago_invoice(customer_address={"postal_code": "98101", "state": "WA", "country": "US"}),
                          [line])
        handle_event(fake, self.engine, self.event("invoiceitem.updated", {"id": "ii_1", "invoice": "in_1"}), {})
        self.assertEqual(fake.updates["il_1"], "")


class RealStripeObjectTest(unittest.TestCase):
    """Runs the adapter on real stripe.StripeObject values when the stripe package is installed."""

    def test_adapter_reads_real_stripe_objects(self):
        try:
            import stripe
        except ImportError:
            self.skipTest("stripe package not installed")
        wrap = lambda d: stripe.StripeObject.construct_from(d, "sk_test_x")
        fake = FakeStripe(chicago_invoice(), [{"id": "il_1", "amount": 5000, "discount_amounts": []}])
        fake.retrieve = lambda invoice_id: wrap(chicago_invoice())
        fake.list = lambda invoice_id, params: FakePage([wrap(fake.lines[0])])
        self.assertEqual(add_tax_to_invoice(fake, TaxEngine(FIXTURES), "in_1"), 525)


if __name__ == "__main__":
    unittest.main()
