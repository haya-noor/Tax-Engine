"""Add tax automatically to every new Stripe invoice, the way Numeral does.

Stripe sends an "invoice.created" event when it makes a draft invoice (for
example each subscription renewal). Subscription invoices stay drafts for about
an hour, and this server adds our tax in that window, before Stripe finalizes.

Try it locally with the Stripe CLI (test mode):

    $env:STRIPE_SECRET_KEY = "sk_test_..."
    stripe listen --api-key $env:STRIPE_SECRET_KEY --events invoice.created,invoice.updated,invoiceitem.created,invoiceitem.deleted --forward-to localhost:4242/webhook
    (it prints a whsec_... secret)
    $env:STRIPE_WEBHOOK_SECRET = "whsec_..."
    python stripe_webhook.py

It also listens for "invoice.updated", "invoiceitem.created" and
"invoiceitem.deleted", so an invoice you build by hand in the Dashboard gets its
tax recalculated each time you add, change or remove an item. (Stripe has no
"invoiceitem.updated" event; a changed price arrives as "invoice.updated".) By the time you
press Send, the tax is on it. (Give it a second or two after the last item.)

To run it for real, without your computer, host it anywhere that runs Python
(set HOST=0.0.0.0 and PORT), or on Vercel through api/webhook.py, and add its https://.../webhook URL in the Stripe
Dashboard under Developers > Webhooks, with the events in EVENTS (adapters/stripe_invoices.py).
"""

import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

import stripe

from adapters.stripe_invoices import EVENTS, handle_event
from taxengine import TaxEngine, WashingtonResolver

PORT = int(os.environ.get("PORT", "4242"))
HOST = os.environ.get("HOST", "localhost")    # 0.0.0.0 when hosted
WEBHOOK_PATHS = ("/webhook", "/api/webhook")   # /api/webhook is how Vercel routes it


def make_handler(client, engine, webhook_secret):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # Health check for the hosting service: "is the server up?"
            self.reply(200, "tax engine webhook: ok")

        def do_POST(self):
            if self.path.split("?")[0] not in WEBHOOK_PATHS:
                return self.reply(404, "not found")
            payload = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                event = stripe.Webhook.construct_event(
                    payload, self.headers.get("Stripe-Signature"), webhook_secret)
            except (ValueError, stripe.SignatureVerificationError):
                return self.reply(400, "bad signature")

            try:
                note = handle_event(client, engine, event.to_dict())
            except Exception as e:     # e.g. a Stripe API error: show it instead of dropping the request
                note = f"{event.type}: failed: {e}"
            if note:
                print(note, flush=True)
            self.reply(200, "ok")

        def reply(self, code, text):
            self.send_response(code)
            self.end_headers()
            self.wfile.write(text.encode())

    return Handler


def from_env():
    """(client, engine, webhook_secret) from environment variables; ValueError if one is missing."""
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not key.startswith(("sk_test_", "rk_test_")) or not secret:
        raise ValueError("Set STRIPE_SECRET_KEY (a test key, sk_test_...) and STRIPE_WEBHOOK_SECRET (whsec_...).")
    collect_in = os.environ.get("TAXENGINE_COLLECT_IN")
    # Washington rates by street address from DOR; set TAXENGINE_DOR_LOOKUP=0 to use ZIP5 only.
    wa = WashingtonResolver.from_files(use_web_lookup=os.environ.get("TAXENGINE_DOR_LOOKUP", "1") != "0")
    engine = TaxEngine(collect_in=collect_in.split(",") if collect_in else None, resolvers={"WA": wa})
    return stripe.StripeClient(key), engine, secret


def main():
    logging.basicConfig(format="note: %(message)s")
    try:
        client, engine, secret = from_env()
    except ValueError as e:
        sys.exit(str(e))
    server = HTTPServer((HOST, PORT), make_handler(client, engine, secret))
    print(f"Listening on http://{HOST}:{PORT}/webhook for: {', '.join(EVENTS)}")
    server.serve_forever()


if __name__ == "__main__":
    main()
