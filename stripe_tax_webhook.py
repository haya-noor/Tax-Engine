"""Add tax automatically to every new Stripe invoice, the way Numeral does.

Stripe sends an "invoice.created" event when it makes a draft invoice (for
example each subscription renewal). Subscription invoices stay drafts for about
an hour, and this server adds our tax in that window, before Stripe finalizes.

Try it locally with the Stripe CLI (test mode):

    $env:STRIPE_SECRET_KEY = "sk_test_..."
    stripe listen --api-key $env:STRIPE_SECRET_KEY --events invoice.created,invoice.updated,invoiceitem.created,invoiceitem.deleted --forward-to localhost:4242/webhook
    (it prints a whsec_... secret)
    $env:STRIPE_WEBHOOK_SECRET = "whsec_..."
    python stripe_tax_webhook.py

It also listens for "invoice.updated", "invoiceitem.created" and
"invoiceitem.deleted", so an invoice you build by hand in the Dashboard gets its
tax recalculated each time you add, change or remove an item. (Stripe has no
"invoiceitem.updated" event; a changed price arrives as "invoice.updated".) By the time you
press Send, the tax is on it. (Give it a second or two after the last item.)

Businesses that install the app from the Stripe Marketplace send their events to
the same /webhook, through a Connect endpoint; backend/event_router.py taxes each
one's invoices with its own settings, kept in Supabase (see docs/supabase.md).

To run it for real, without your computer, host it: on Vercel through
api/vercel_handler.py (see docs/hosting.md), or anywhere that runs Python with
HOST=0.0.0.0 and PORT set. Then add its https://.../webhook URL in the Stripe
Dashboard under Developers > Webhooks, with the events in EVENTS (adapters/stripe_invoice_tax.py).
"""

import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

import stripe

from adapters.stripe_invoice_tax import EVENTS
from backend.account_store import SupabaseStore
from backend.event_router import INSTALL_EVENTS, UNINSTALL_EVENTS, EventRouter
from backend.settings_api import SETTINGS_PATHS, handle_settings
from taxengine import TaxEngine, address_resolvers

PORT = int(os.environ.get("PORT", "4242"))
HOST = os.environ.get("HOST", "localhost")    # 0.0.0.0 when hosted
WEBHOOK_PATHS = ("/webhook",)


def verify(payload, signature, secrets):
    """The event, if it is signed with one of the secrets (each Stripe endpoint has its own)."""
    for secret in secrets:
        try:
            return stripe.Webhook.construct_event(payload, signature, secret)
        except stripe.SignatureVerificationError:
            continue
    raise stripe.SignatureVerificationError("no matching signing secret", signature)


def make_handler(router, webhook_secrets, app_secret=None):
    """The HTTP handler: Stripe webhooks on /webhook, the app's settings screen on /settings/*.

    app_secret is the Stripe App's signing secret (absec_...), for the settings screen.
    """
    if isinstance(webhook_secrets, str):
        webhook_secrets = [webhook_secrets]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # Health check for the hosting service: "is the server up?"
            self.reply(200, "tax engine webhook: ok")

        def do_OPTIONS(self):
            # CORS preflight from the settings screen in the Stripe Dashboard.
            self.send_response(204)
            self.cors_headers()
            self.end_headers()

        def do_POST(self):
            path = self.path.split("?")[0]
            payload = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if path in SETTINGS_PATHS:
                status, data = handle_settings(path, payload, self.headers.get("Stripe-Signature"),
                                               router.store, app_secret)
                return self.reply(status, json.dumps(data), "application/json")
            if path not in WEBHOOK_PATHS:
                return self.reply(404, "not found")
            try:
                event = verify(payload, self.headers.get("Stripe-Signature"), webhook_secrets)
            except (ValueError, stripe.SignatureVerificationError):
                return self.reply(400, "bad signature")

            try:
                note = router.handle(event.to_dict())
            except Exception as e:     # e.g. a Stripe API error: show it instead of dropping the request
                note = f"{event.type}: failed: {e}"
            if note:
                print(note, flush=True)
            self.reply(200, "ok")

        def cors_headers(self):
            # Every settings request is authenticated by its Stripe signature, so any origin is fine.
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Stripe-Signature")

        def reply(self, code, text, content_type="text/plain"):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.cors_headers()
            self.end_headers()
            self.wfile.write(text.encode())

    return Handler


def from_env():
    """(router, webhook_secrets, app_secret) from environment variables; ValueError if one is missing.

    STRIPE_CONNECT_WEBHOOK_SECRET is the signing secret of the Connect endpoint that
    receives events from businesses that installed the app; STRIPE_APP_SECRET (absec_...)
    checks requests from the app's settings screen. SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are optional: without them only the
    platform's own account is served, not businesses that installed the app.
    """
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not key.startswith(("sk_test_", "rk_test_")) or not secret:
        raise ValueError("Set STRIPE_SECRET_KEY (a test key, sk_test_...) and STRIPE_WEBHOOK_SECRET (whsec_...).")
    collect_in = os.environ.get("TAXENGINE_COLLECT_IN")
    # Rates by street address where a state has its own source (Washington: DOR).
    # TAXENGINE_DOR_LOOKUP=0 turns the web lookups off and uses the files and ZIP tables only.
    resolvers = address_resolvers(use_web_lookup=os.environ.get("TAXENGINE_DOR_LOOKUP", "1") != "0")
    engine = TaxEngine(collect_in=collect_in.split(",") if collect_in else None, resolvers=resolvers)
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    store = SupabaseStore(supabase_url, supabase_key) if supabase_url and supabase_key else None
    secrets = [secret] + [s for s in [os.environ.get("STRIPE_CONNECT_WEBHOOK_SECRET", "").strip()] if s]
    app_secret = os.environ.get("STRIPE_APP_SECRET", "").strip() or None
    return EventRouter(key, engine, store, resolvers), secrets, app_secret


def main():
    logging.basicConfig(format="note: %(message)s")
    try:
        router, secrets, app_secret = from_env()
    except ValueError as e:
        sys.exit(str(e))
    server = HTTPServer((HOST, PORT), make_handler(router, secrets, app_secret))
    events = EVENTS + INSTALL_EVENTS + UNINSTALL_EVENTS
    print(f"Listening on http://{HOST}:{PORT}/webhook for: {', '.join(events)}")
    if router.store is None:
        print("No SUPABASE_URL: serving this Stripe account only, not app installs.")
    server.serve_forever()


if __name__ == "__main__":
    main()
