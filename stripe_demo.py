"""Create a test invoice in Stripe with tax from the engine.

Uses Stripe test mode only: no real money moves. Needs a test secret key:

    pip install -r requirements-stripe.txt
    $env:STRIPE_SECRET_KEY = "sk_test_..."          (PowerShell)
    python stripe_demo.py
    python stripe_demo.py --zip 98101 --state WA --item "Hoodie=59.99" --item "Shipping=8.00"

It creates a customer at the given address, a draft invoice with the items,
adds our tax to each line, finalizes it, and prints the invoice link.
"""

import argparse
import os
import sys

import stripe

from adapters.stripe_invoices import add_tax_to_invoice, to_cents
from taxengine import TaxEngine


def parse_item(text):
    name, _, price = text.partition("=")
    if not price:
        raise argparse.ArgumentTypeError(f"Use NAME=PRICE, e.g. 'T-shirt=25.00', not {text!r}")
    return name, price


def main():
    parser = argparse.ArgumentParser(description="Make a Stripe test-mode invoice with tax from the engine")
    parser.add_argument("--zip", default="60601")
    parser.add_argument("--state", default="IL")
    parser.add_argument("--city", default="Chicago")
    parser.add_argument("--item", action="append", type=parse_item,
                        help="NAME=PRICE, repeat for several items (default: two sample items)")
    parser.add_argument("--collect-in", help="states you collect tax in, comma separated (default: all)")
    parser.add_argument("--keep-draft", action="store_true", help="don't finalize, so you can inspect the draft")
    args = parser.parse_args()

    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key.startswith(("sk_test_", "rk_test_")):
        sys.exit("Set STRIPE_SECRET_KEY to a Stripe TEST key (sk_test_...). Live keys are refused.")
    client = stripe.StripeClient(key)
    engine = TaxEngine(collect_in=args.collect_in.split(",") if args.collect_in else None)
    items = args.item or [("T-shirt", "25.00"), ("Hoodie", "59.99")]

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
    for name, price in items:
        client.v1.invoice_items.create({
            "customer": customer.id, "invoice": invoice.id, "currency": "usd",
            "amount": to_cents(price), "description": name,
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
