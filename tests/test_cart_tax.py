import unittest
from decimal import Decimal
from pathlib import Path

from taxengine import CartLine, TaxEngine, UnknownCategoryError, calculate_cart, load_taxability, taxability_files
from adapters.stripe_tax_codes import STRIPE_TAX_CODES
from taxengine.shared.product_taxability import rule_for

FIXTURES = Path(__file__).parent / "fixtures" / "rates"
D = Decimal


class WashingtonCartTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = TaxEngine(FIXTURES)

    def cart(self, lines, shipping=0):
        return calculate_cart(self.engine, "98101", "WA", lines, shipping=shipping)

    def test_clothing_taxed_food_exempt(self):
        result = self.cart([CartLine("shirt", "25.00", category="clothing"),
                            CartLine("bread", "5.00", category="food_and_food_ingredients")])
        self.assertEqual([(t.line_id, t.taxable, t.tax.total_tax) for t in result.lines],
                         [("shirt", True, D("2.64")), ("bread", False, D("0.00"))])   # 25 x 10.55% = 2.6375
        self.assertEqual(result.total_tax, D("2.64"))
        self.assertEqual(result.total, D("32.64"))

    def test_quantity_and_discount(self):
        result = self.cart([CartLine("shirt", "25.00", quantity=2, discount="5.00", category="clothing")])
        self.assertEqual(result.lines[0].tax.amount, D("45.00"))
        self.assertEqual(result.total_tax, D("4.75"))           # 45 x 10.55% = 4.7475

    def test_shipping_taxed_in_proportion_to_taxable_goods(self):
        result = self.cart([CartLine("shirt", "45.00", category="clothing"),
                            CartLine("bread", "5.00", category="food_and_food_ingredients")], shipping="8.00")
        self.assertEqual(result.shipping.tax.amount, D("7.20"))  # 90% of the goods are taxable
        self.assertEqual(result.shipping.tax.total_tax, D("0.76"))
        self.assertEqual(result.subtotal, D("58.00"))

    def test_shipping_for_only_exempt_goods_is_exempt(self):
        result = self.cart([CartLine("bread", "5.00", category="food_and_food_ingredients")], shipping="8.00")
        self.assertFalse(result.shipping.taxable)
        self.assertEqual(result.total_tax, D("0.00"))

    def test_untagged_products_are_general_and_taxed(self):
        self.assertEqual(self.cart([CartLine("lamp", "100")]).total_tax, D("10.55"))

    def test_unknown_category_is_an_error(self):
        with self.assertRaises(UnknownCategoryError):
            self.cart([CartLine("x", "1", category="spaceships")])

    def test_states_we_dont_collect_in_get_no_tax(self):
        engine = TaxEngine(FIXTURES, collect_in={"WA"})
        result = calculate_cart(engine, "88240", "TX", [CartLine("shirt", "25", category="general")], shipping="5")
        self.assertEqual(result.total_tax, D("0.00"))


class StatesWithoutRulesTest(unittest.TestCase):
    def test_general_and_shipping_taxed_other_categories_refused(self):
        engine = TaxEngine(FIXTURES)
        result = calculate_cart(engine, "60601", "IL", [CartLine("lamp", "100")], shipping="10")
        self.assertEqual(result.total_tax, D("11.55"))          # 10.50 + 1.05
        with self.assertRaises(UnknownCategoryError):
            calculate_cart(engine, "60601", "IL", [CartLine("bread", "5", category="food_and_food_ingredients")])


class WashingtonRuleFileTest(unittest.TestCase):
    def test_every_rule_is_valid_and_cites_a_source(self):
        rules = load_taxability(taxability_files())["WA"]
        self.assertIn("general", rules)
        self.assertEqual(rules["delivery_charges"].taxable, "proportional")
        self.assertEqual(rules["food_and_food_ingredients"].taxable, "no")
        self.assertEqual(rules["candy"].taxable, "no")
        self.assertEqual((rules["candy"].basis, rules["candy"].ref), ("sst", "40010"))
        for rule in rules.values():
            self.assertTrue(rule.source.startswith("https://"), rule.category)

    def test_every_category_comes_from_an_official_source(self):
        rules = load_taxability(taxability_files())
        for name, rule in rules["WA"].items():
            if rule.basis == "sst":
                self.assertTrue(rule.ref.isdigit(), name)
            elif rule.basis == "stripe":
                self.assertRegex(rule.ref, r"^txcd_\d{8}$", name)
            else:
                self.assertEqual(rule.basis, "state_law", name)
                self.assertTrue(rule.ref.startswith("RCW "), name)
        with self.assertRaises(UnknownCategoryError):
            rule_for(rules, "WA", "groceries")     # unofficial names are refused, not guessed
        self.assertEqual(rule_for(rules, "WA", " Candy ").category, "candy")

    def test_every_mapped_stripe_code_has_a_washington_rule(self):
        rules = load_taxability(taxability_files())["WA"]
        for code, category in STRIPE_TAX_CODES.items():
            self.assertIn(category, rules, code)

if __name__ == "__main__":
    unittest.main()
