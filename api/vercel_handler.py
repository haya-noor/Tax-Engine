"""Vercel entry point for the Stripe webhook (see docs/hosting.md).

pyproject.toml points Vercel at `handler` below. It uses the same request
handling as stripe_tax_webhook.py. Settings come from the project's environment
variables: STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, TAXENGINE_COLLECT_IN (and
optionally TAXENGINE_DOR_LOOKUP=0).
"""

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
        """Settings are missing: say so on every request instead of crashing."""

        def do_GET(self):
            self.reply(500, f"tax engine webhook: not configured. {_problem}")

        do_POST = do_GET

        def reply(self, code, text):
            self.send_response(code)
            self.end_headers()
            self.wfile.write(text.encode())


class handler(BaseHTTPRequestHandler):
    do_GET = _impl.do_GET
    do_POST = _impl.do_POST
    reply = _impl.reply
