"""Create a test invoice in Stripe with tax from the engine.

Uses Stripe test mode only: no real money moves. Needs a test secret key:

    pip install -r requirements-stripe.txt
    $env:STRIPE_SECRET_KEY = "sk_test_..."          (PowerShell)
    python stripe_demo.py                                   (Seattle, WA sample cart)
    python stripe_demo.py --item "Hoodie=59.99:clothing" --item "Bread=4.50:groceries" --shipping 8.00
    python stripe_demo.py --zip 60601 --state IL --city Chicago --collect-in IL

It creates a customer at the given address, a draft invoice with the items,
adds our tax to each line, finalizes it, and prints the invoice link.
"""

import argparse
import os
import sys

import stripe

from adapters.stripe_invoices import CATEGORY_KEY, add_tax_to_invoice, to_cents
from taxengine import TaxEngine


def parse_item(text):
    """NAME=PRICE or NAME=PRICE:CATEGORY, e.g. 'Bread=4.50:groceries'."""
    name, _, rest = text.partition("=")
    price, _, category = rest.partition(":")
    if not price:
        raise argparse.ArgumentTypeError(f"Use NAME=PRICE[:CATEGORY], e.g. 'Bread=4.50:groceries', not {text!r}")
    return name, price, category or "general"


def main():
    parser = argparse.ArgumentParser(description="Make a Stripe test-mode invoice with tax from the engine")
    parser.add_argument("--zip", default="98101")
    parser.add_argument("--state", default="WA")
    parser.add_argument("--city", default="Seattle")
    parser.add_argument("--item", action="append", type=parse_item,
                        help="NAME=PRICE[:CATEGORY], repeat for several items (default: a sample cart)")
    parser.add_argument("--shipping", help="shipping charge, e.g. 8.00 (default: 8.00 with the sample cart)")
    parser.add_argument("--collect-in", default="WA", help="states you collect tax in, comma separated (default: WA)")
    parser.add_argument("--keep-draft", action="store_true", help="don't finalize, so you can inspect the draft")
    args = parser.parse_args()

    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key.startswith(("sk_test_", "rk_test_")):
        sys.exit("Set STRIPE_SECRET_KEY to a Stripe TEST key (sk_test_...). Live keys are refused.")
    client = stripe.StripeClient(key)
    engine = TaxEngine(collect_in=args.collect_in.split(","))
    items = args.item or [("T-shirt", "25.00", "clothing"), ("Bread", "4.50", "groceries"),
                          ("Ebook", "9.99", "digital_goods")]
    shipping = args.shipping or (None if args.item else "8.00")
    if shipping:
        items.append(("Shipping", shipping, "shipping"))

    customer = client.v1.customers.create({
        "name": "Tax Engine Test Customer",
        "email": "tax-engine-test@example.com",   # Stripe needs one to send an invoice
        "address": {"line1": "100 Test St", "city": args.city, "state": args.state,
                    "postal_code": args.zip, "country": "US"},
    })
    invoice = client.v1.invoices.create({
        "customer": customer.id,
        "collection_method": "send_invoice",
        "days_until_due": 30,
        "auto_advance": False,
        "description": "Created by the tax engine's Stripe demo",
    })
    for name, price, category in items:
        client.v1.invoice_items.create({
            "customer": customer.id, "invoice": invoice.id, "currency": "usd",
            "amount": to_cents(price), "description": name,
            "metadata": {CATEGORY_KEY: category},
        })

    tax_cents = add_tax_to_invoice(client, engine, invoice.id)
    if not args.keep_draft:
        invoice = client.v1.invoices.finalize_invoice(invoice.id)
    else:
        invoice = client.v1.invoices.retrieve(invoice.id)

    print(f"Invoice {invoice.id} ({invoice.status}) for ZIP {args.zip}, {args.state}")
    print(f"  Subtotal:  {invoice.subtotal / 100:>10.2f}")
    print(f"  Our tax:   {tax_cents / 100:>10.2f}")
    print(f"  Total:     {invoice.total / 100:>10.2f}")
    print(f"Dashboard: https://dashboard.stripe.com/test/invoices/{invoice.id}")
    if invoice.to_dict().get("hosted_invoice_url"):
        print(f"Customer view: {invoice.hosted_invoice_url}")


if __name__ == "__main__":
    main()
