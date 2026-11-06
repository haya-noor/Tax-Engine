"""Tax for a whole cart: several lines, quantities, discounts, categories and shipping.

Each line is taxed on its own and rounded to the cent (per-line rounding), so
the cart total is the sum of the lines. Product categories decide whether a
line is taxed (see taxability.py); shipping follows the state's shipping rule.
"""

from dataclasses import dataclass
from decimal import Decimal

from .core import money, normalize_zip, untaxed
from .taxability import GENERAL, SHIPPING, rule_for


@dataclass(frozen=True)
class CartLine:
    id: str
    unit_price: Decimal
    quantity: int = 1
    discount: Decimal = Decimal("0")     # total discount on the line, not per unit
    category: str = GENERAL

    @property
    def net(self):
        return money(Decimal(str(self.unit_price)) * self.quantity - Decimal(str(self.discount)))


@dataclass(frozen=True)
class LineTax:
    line_id: str
    category: str
    taxable: bool
    tax: object          # TaxResult; its .amount is the taxed amount


@dataclass(frozen=True)
class CartResult:
    state: str
    zip_code: str
    lines: list          # LineTax per cart line
    shipping: object     # LineTax for shipping, or None
    subtotal: Decimal    # lines after discounts, plus shipping
    total_tax: Decimal

    @property
    def total(self):
        return self.subtotal + self.total_tax

    def __str__(self):
        out = [f"Cart for ZIP {self.zip_code}, {self.state}"]
        for t in self.lines + ([self.shipping] if self.shipping else []):
            label = "taxed" if t.taxable else "exempt"
            out.append(f"  {t.line_id:<20} {t.category:<20} {label:<7} {t.tax.total_tax:>8}")
        out.append(f"Subtotal:   {self.subtotal:>10}")
        out.append(f"Total tax:  {self.total_tax:>10}")
        out.append(f"Total:      {self.total:>10}")
        return "\n".join(out)


def calculate_cart(engine, zip_code, state, lines, shipping=0):
    """Tax every line of a cart, plus shipping, for one shipping address."""
    state = state.upper()
    zip_code = normalize_zip(zip_code)
    results = [_tax_line(engine, zip_code, state, line.id, line.net, line.category) for line in lines]

    shipping_tax = None
    shipping = money(shipping)
    if shipping:
        shipping_tax = _tax_shipping(engine, zip_code, state, shipping, results)

    all_taxes = results + ([shipping_tax] if shipping_tax else [])
    return CartResult(
        state=state,
        zip_code=zip_code,
        lines=results,
        shipping=shipping_tax,
        subtotal=sum((line.net for line in lines), money(0)) + shipping,
        total_tax=sum((t.tax.total_tax for t in all_taxes), money(0)),
    )


def _tax_line(engine, zip_code, state, line_id, amount, category):
    rule = rule_for(engine.taxability, state, category)
    if rule.taxable == "yes":
        return LineTax(line_id, rule.category, True, engine.calculate(zip_code, amount, state=state))
    reason = f"exempt: {rule.category}"
    return LineTax(line_id, rule.category, False, untaxed(zip_code, state, amount, engine.rate_version, reason))


def _tax_shipping(engine, zip_code, state, shipping, results):
    rule = rule_for(engine.taxability, state, SHIPPING)
    if rule.taxable != "proportional":
        return _tax_line(engine, zip_code, state, SHIPPING, shipping, SHIPPING)
    # Taxed in the same share as the goods, by price.
    goods = sum((t.tax.amount for t in results), money(0))
    taxable_goods = sum((t.tax.amount for t in results if t.taxable), money(0))
    share = taxable_goods / goods if goods > 0 else Decimal(0)
    taxable_part = money(shipping * share)
    if not taxable_part:
        reason = "exempt: shipping for exempt goods"
        return LineTax(SHIPPING, SHIPPING, False, untaxed(zip_code, state, shipping, engine.rate_version, reason))
    return LineTax(SHIPPING, SHIPPING, True, engine.calculate(zip_code, taxable_part, state=state))
