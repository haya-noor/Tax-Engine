"""Add tax automatically to every new Stripe invoice, the way Numeral does.

Stripe sends an "invoice.created" event when it makes a draft invoice (for
example each subscription renewal). Subscription invoices stay drafts for about
an hour, and this server adds our tax in that window, before Stripe finalizes.

Try it locally with the Stripe CLI (test mode):

    $env:STRIPE_SECRET_KEY = "sk_test_..."
    stripe listen --forward-to localhost:4242/webhook      (prints a whsec_... secret)
    $env:STRIPE_WEBHOOK_SECRET = "whsec_..."
    python stripe_webhook.py

Invoices you create by hand in the Dashboard get the event before you add
items, so for those use stripe_demo.py or call add_tax_to_invoice() yourself.
"""

import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

import stripe

from adapters.stripe_invoices import NoTaxAddressError, add_tax_to_invoice
from taxengine import TaxEngine

PORT = int(os.environ.get("PORT", "4242"))


def make_handler(client, engine, webhook_secret):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/webhook":
                return self.reply(404, "not found")
            payload = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                event = stripe.Webhook.construct_event(
                    payload, self.headers.get("Stripe-Signature"), webhook_secret)
            except (ValueError, stripe.SignatureVerificationError):
                return self.reply(400, "bad signature")

            if event.type == "invoice.created":
                invoice = event.data.object
                if invoice.status == "draft" and not (invoice.get("automatic_tax") or {}).get("enabled"):
                    try:
                        cents = add_tax_to_invoice(client, engine, invoice.id)
                        print(f"{invoice.id}: added tax {cents / 100:.2f}")
                    except (NoTaxAddressError, LookupError) as e:
                        print(f"{invoice.id}: no tax added: {e}")
            self.reply(200, "ok")

        def reply(self, code, text):
            self.send_response(code)
            self.end_headers()
            self.wfile.write(text.encode())

    return Handler


def main():
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not key.startswith(("sk_test_", "rk_test_")) or not secret:
        sys.exit("Set STRIPE_SECRET_KEY (a test key, sk_test_...) and STRIPE_WEBHOOK_SECRET (whsec_...).")
    collect_in = os.environ.get("TAXENGINE_COLLECT_IN")
    engine = TaxEngine(collect_in=collect_in.split(",") if collect_in else None)
    server = HTTPServer(("localhost", PORT), make_handler(stripe.StripeClient(key), engine, secret))
    print(f"Listening on http://localhost:{PORT}/webhook")
    server.serve_forever()


if __name__ == "__main__":
    main()
