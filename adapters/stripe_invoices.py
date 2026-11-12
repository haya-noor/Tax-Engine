"""Stripe adapter: add the engine's sales tax to a draft Stripe invoice.

For each line on the invoice, the engine works out the tax from the customer's
address and the line's product category, and writes it to the line as Stripe
"manual tax amounts", one per layer (state, county, city, special district).
The invoice must still be a draft: Stripe doesn't allow tax changes after it
is finalized.

Stripe's guide: https://docs.stripe.com/invoicing/taxes/manual-tax-amounts
"""

from decimal import Decimal

from taxengine import Address, CartLine, calculate_cart, money
from taxengine.taxability import GENERAL, SHIPPING

CATEGORY_KEY = "tax_category"
STRIPE_LEVEL = {"state": "state", "county": "county", "city": "city", "special": "district", "local": "multiple"}
LAYER_NAME = {"state": "State", "county": "County", "city": "City", "special": "Special district", "local": "Local"}


class NoTaxAddressError(ValueError):
    """The invoice has no US address with a ZIP code and state to tax."""


def plain(obj):
    """Stripe's objects aren't dicts (no .get); work on a plain dict copy."""
    return obj.to_dict() if hasattr(obj, "to_dict") else obj


def to_cents(dollars):
    return int(money(dollars) * 100)


def to_dollars(cents):
    return Decimal(cents) / 100


def invoice_street_address(invoice):
    """The address to tax, as an Address: the shipping address if there is one, else the billing address."""
    shipping = invoice.get("customer_shipping") or {}
    address = shipping.get("address") or invoice.get("customer_address") or {}
    if address.get("country") not in (None, "US") or not address.get("postal_code") or not address.get("state"):
        raise NoTaxAddressError(f"Invoice {invoice.get('id')} has no US address with a ZIP code and state")
    return Address(address.get("line1") or "", address.get("city") or "", address["state"], address["postal_code"])


def invoice_address(invoice):
    """The (ZIP code, state) to tax."""
    address = invoice_street_address(invoice)
    return address.zip_code, address.state


def taxable_cents(line):
    """The line's amount after discounts, in cents."""
    discounts = sum(d["amount"] for d in line.get("discount_amounts") or [])
    return line["amount"] - discounts


def jurisdiction_name(result):
    """ZIP tables use upper-case names (SEATTLE -> Seattle); address sources are already readable."""
    return result.region.title() if result.source == "zip5" else result.region


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
                "jurisdiction": result.state if layer.layer == "state" else jurisdiction_name(result),
                "jurisdiction_level": STRIPE_LEVEL[layer.layer],
                "country": "US",
                "state": result.state,
            },
        })
    return amounts


def line_category(client, line):
    """The product category from metadata, e.g. {"tax_category": "groceries"}.

    Read from the line, or else from the invoice item it came from.
    """
    metadata = line.get("metadata") or {}
    if CATEGORY_KEY not in metadata:
        item_id = ((line.get("parent") or {}).get("invoice_item_details") or {}).get("invoice_item")
        if item_id:
            metadata = plain(client.v1.invoice_items.retrieve(item_id)).get("metadata") or {}
    return metadata.get(CATEGORY_KEY) or GENERAL


def add_tax_to_invoice(client, engine, invoice_id, memo=None):
    """Calculate and set tax on every line of a draft invoice. Returns total tax in cents.

    client is a stripe.StripeClient; engine is a taxengine.TaxEngine. Each line's
    product category comes from its "tax_category" metadata (default "general");
    lines with category "shipping" are delivery charges.
    """
    invoice = plain(client.v1.invoices.retrieve(invoice_id))
    if invoice["status"] != "draft":
        raise ValueError(f"Invoice {invoice_id} is {invoice['status']}; tax can only be set on drafts")
    if (invoice.get("automatic_tax") or {}).get("enabled"):
        raise ValueError(f"Invoice {invoice_id} has 'Collect tax automatically' (Stripe Tax) on; "
                         "turn it off so this engine can set the tax")
    address = invoice_street_address(invoice)
    zip_code, state = address.zip_code, address.state

    lines = [plain(line) for line in client.v1.invoices.line_items.list(invoice_id, {"limit": 100}).auto_paging_iter()]
    lines = [line for line in lines if taxable_cents(line) > 0]    # credits and free lines carry no tax
    categories = {line["id"]: line_category(client, line) for line in lines}
    goods = [CartLine(line["id"], to_dollars(taxable_cents(line)), category=categories[line["id"]])
             for line in lines if categories[line["id"]] != SHIPPING]

    taxes = {t.line_id: t for t in calculate_cart(engine, zip_code, state, goods, address=address).lines}
    for line in lines:
        if categories[line["id"]] == SHIPPING:
            shipping = calculate_cart(engine, zip_code, state, goods, shipping=to_dollars(taxable_cents(line)),
                                      address=address).shipping
            taxes[line["id"]] = shipping

    total = 0
    by_id = {line["id"]: line for line in lines}
    for line_id, line_tax in taxes.items():
        amounts = tax_amounts_for(line_tax.tax) if line_tax.taxable else []
        total += sum(a["amount"] for a in amounts)
        wanted = sorted((a["amount"], a["taxable_amount"]) for a in amounts)
        # Skip when the tax is already right. Each write makes Stripe send another
        # event, so writing the same tax again would loop. memo remembers what we
        # last wrote, in case Stripe reports a line's tax in a shape we don't read.
        if current_tax(by_id[line_id]) == wanted or (memo is not None and memo.get((invoice_id, line_id)) == wanted):
            continue
        # An empty string removes tax that is no longer due (e.g. the item became exempt).
        client.v1.invoices.line_items.update(invoice_id, line_id, {"tax_amounts": amounts or ""})
        if memo is not None:
            memo[(invoice_id, line_id)] = wanted
    return total


def current_tax(line):
    """The (amount, taxable_amount) pairs of the tax already on a line, sorted."""
    taxes = line.get("taxes") or line.get("tax_amounts") or []
    return sorted((t.get("amount"), t.get("taxable_amount")) for t in taxes)


# Webhook events that can change the tax on a draft invoice.
# Stripe has no "invoiceitem.updated" event: a changed item arrives as invoice.updated.
EVENTS = ("invoice.created", "invoice.updated", "invoiceitem.created", "invoiceitem.deleted")


def invoice_to_tax(event):
    """The draft invoice id an event is about, or None if there is nothing to do."""
    obj = event["data"]["object"]
    # invoice.updated covers edits the Dashboard makes to a draft's lines directly
    # (e.g. changing a price) and switching "Collect tax automatically" off.
    if event["type"] in ("invoice.created", "invoice.updated"):
        if obj.get("status") == "draft" and not (obj.get("automatic_tax") or {}).get("enabled"):
            return obj["id"]
        return None
    if event["type"].startswith("invoiceitem."):
        invoice = obj.get("invoice")
        return invoice if isinstance(invoice, str) else (invoice or {}).get("id")
    return None


_WRITTEN = {}    # (invoice id, line id) -> tax last written by handle_event


def handle_event(client, engine, event, memo=_WRITTEN):
    """Add or refresh the tax on the invoice an event is about. Returns a log line."""
    invoice_id = invoice_to_tax(event)
    if not invoice_id:
        return None
    try:
        cents = add_tax_to_invoice(client, engine, invoice_id, memo)
        return f"{invoice_id}: tax {cents / 100:.2f} ({event['type']})"
    except (NoTaxAddressError, LookupError) as e:
        return f"{invoice_id}: no tax added: {e}"
    except ValueError as e:     # e.g. already finalized: tax can only change on drafts
        return f"{invoice_id}: {e}"
