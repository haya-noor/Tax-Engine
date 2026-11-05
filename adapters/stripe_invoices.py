"""Stripe adapter: add the engine's sales tax to a draft Stripe invoice.

For each line on the invoice, the engine works out the tax from the customer's
address, and the tax is written to the line as Stripe "manual tax amounts",
one per layer (state, county, city, special district). The invoice must still
be a draft: Stripe doesn't allow tax changes after it is finalized.

Stripe's guide: https://docs.stripe.com/invoicing/taxes/manual-tax-amounts
"""

from decimal import Decimal

from taxengine import money

STRIPE_LEVEL = {"state": "state", "county": "county", "city": "city", "special": "district"}
LAYER_NAME = {"state": "State", "county": "County", "city": "City", "special": "Special district"}


class NoTaxAddressError(ValueError):
    """The invoice has no US address with a ZIP code and state to tax."""


def plain(obj):
    """Stripe's objects aren't dicts (no .get); work on a plain dict copy."""
    return obj.to_dict() if hasattr(obj, "to_dict") else obj


def to_cents(dollars):
    return int(money(dollars) * 100)


def to_dollars(cents):
    return Decimal(cents) / 100


def invoice_address(invoice):
    """The address to tax: the shipping address if there is one, else the billing address."""
    shipping = invoice.get("customer_shipping") or {}
    address = shipping.get("address") or invoice.get("customer_address") or {}
    if address.get("country") not in (None, "US") or not address.get("postal_code") or not address.get("state"):
        raise NoTaxAddressError(f"Invoice {invoice.get('id')} has no US address with a ZIP code and state")
    return address["postal_code"], address["state"]


def taxable_cents(line):
    """The line's amount after discounts, in cents."""
    discounts = sum(d["amount"] for d in line.get("discount_amounts") or [])
    return line["amount"] - discounts


def tax_amounts_for(result):
    """Turn an engine TaxResult into Stripe's tax_amounts list for one line."""
    amounts = []
    for layer in result.balanced_layers():
        name = LAYER_NAME[layer.layer]
        amounts.append({
            "amount": to_cents(layer.tax),
            "taxable_amount": to_cents(result.amount),
            "tax_rate_data": {
                "display_name": f"{name} sales tax",
                "description": f"{name} sales tax, {result.region}",
                "percentage": float(layer.rate * 100),
                "inclusive": False,
                "tax_type": "sales_tax",
                "jurisdiction": result.state if layer.layer == "state" else result.region.title(),
                "jurisdiction_level": STRIPE_LEVEL[layer.layer],
                "country": "US",
                "state": result.state,
            },
        })
    return amounts


def add_tax_to_invoice(client, engine, invoice_id):
    """Calculate and set tax on every line of a draft invoice. Returns total tax in cents.

    client is a stripe.StripeClient; engine is a taxengine.TaxEngine.
    """
    invoice = plain(client.v1.invoices.retrieve(invoice_id))
    if invoice["status"] != "draft":
        raise ValueError(f"Invoice {invoice_id} is {invoice['status']}; tax can only be set on drafts")
    zip_code, state = invoice_address(invoice)

    total = 0
    for line in client.v1.invoices.line_items.list(invoice_id, {"limit": 100}).auto_paging_iter():
        line = plain(line)
        cents = taxable_cents(line)
        if cents <= 0:
            continue    # credits and free lines carry no tax
        amounts = tax_amounts_for(engine.calculate(zip_code, to_dollars(cents), state=state))
        if not amounts:
            continue    # a state we don't collect in
        client.v1.invoices.line_items.update(invoice_id, line["id"], {"tax_amounts": amounts})
        total += sum(a["amount"] for a in amounts)
    return total
