"""Vercel entry point for the Stripe webhook (see docs/hosting.md).

pyproject.toml points Vercel at `handler` below. It uses the same request
handling as stripe_tax_webhook.py. Settings come from the project's environment
variables: STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, TAXENGINE_COLLECT_IN,
SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, STRIPE_CONNECT_WEBHOOK_SECRET and
STRIPE_APP_SECRET (and optionally TAXENGINE_DOR_LOOKUP=0).
"""

import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stripe_tax_webhook import from_env, make_handler  # noqa: E402

logging.basicConfig(format="note: %(message)s")

try:
    _impl = make_handler(*from_env())
except ValueError as e:
    _problem = str(e)

    class _impl(BaseHTTPRequestHandler):
        """Settings are missing: say so on every request instead of crashing.

        The reply is JSON with CORS headers, so the app's settings screen shows the
        problem instead of a bare "Failed to fetch".
        """

        def do_GET(self):
            self.reply(500, json.dumps({"error": f"server not configured: {_problem}"}))

        do_POST = do_GET

        def do_OPTIONS(self):
            self.send_response(204)
            self.cors_headers()
            self.end_headers()

        def cors_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Stripe-Signature")

        def reply(self, code, text):
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.cors_headers()
            self.end_headers()
            self.wfile.write(text.encode())


class handler(BaseHTTPRequestHandler):
    do_GET = _impl.do_GET
    do_POST = _impl.do_POST
    do_OPTIONS = _impl.do_OPTIONS
    reply = _impl.reply
    cors_headers = _impl.cors_headers
