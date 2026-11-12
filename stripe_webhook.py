"""Add tax automatically to every new Stripe invoice, the way Numeral does.

Stripe sends an "invoice.created" event when it makes a draft invoice (for
example each subscription renewal). Subscription invoices stay drafts for about
an hour, and this server adds our tax in that window, before Stripe finalizes.

Try it locally with the Stripe CLI (test mode):

    $env:STRIPE_SECRET_KEY = "sk_test_..."
    stripe listen --api-key $env:STRIPE_SECRET_KEY --events invoice.created,invoiceitem.created,invoiceitem.updated,invoiceitem.deleted --forward-to localhost:4242/webhook
    (it prints a whsec_... secret)
    $env:STRIPE_WEBHOOK_SECRET = "whsec_..."
    python stripe_webhook.py

It also listens for "invoiceitem.created", "invoiceitem.updated" and
"invoiceitem.deleted", so an invoice you build by hand in the Dashboard gets its
tax recalculated each time you add, change or remove an item. By the time you
press Send, the tax is on it. (Give it a second or two after the last item.)

To run it for real, without your computer, host it anywhere that runs Python
(set HOST=0.0.0.0 and PORT), and add its https://.../webhook URL in the Stripe
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

            note = handle_event(client, engine, event.to_dict())
            if note:
                print(note, flush=True)
            self.reply(200, "ok")

        def reply(self, code, text):
            self.send_response(code)
            self.end_headers()
            self.wfile.write(text.encode())

    return Handler


def main():
    logging.basicConfig(format="note: %(message)s")
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not key.startswith(("sk_test_", "rk_test_")) or not secret:
        sys.exit("Set STRIPE_SECRET_KEY (a test key, sk_test_...) and STRIPE_WEBHOOK_SECRET (whsec_...).")
    collect_in = os.environ.get("TAXENGINE_COLLECT_IN")
    # Washington rates by street address from DOR; set TAXENGINE_DOR_LOOKUP=0 to use ZIP5 only.
    wa = WashingtonResolver.from_files(use_web_lookup=os.environ.get("TAXENGINE_DOR_LOOKUP", "1") != "0")
    engine = TaxEngine(collect_in=collect_in.split(",") if collect_in else None, resolvers={"WA": wa})
    server = HTTPServer((HOST, PORT), make_handler(stripe.StripeClient(key), engine, secret))
    print(f"Listening on http://{HOST}:{PORT}/webhook for: {', '.join(EVENTS)}")
    server.serve_forever()


if __name__ == "__main__":
    main()
