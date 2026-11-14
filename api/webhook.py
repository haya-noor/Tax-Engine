"""Vercel entry point for the Stripe webhook (see docs/hosting.md).

Vercel runs this file on each request instead of a long-running server, using
the same request handler as stripe_webhook.py. Settings come from the project's
environment variables: STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET,
TAXENGINE_COLLECT_IN (and optionally TAXENGINE_DOR_LOOKUP=0).
"""

import logging
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stripe_webhook import from_env, make_handler  # noqa: E402

logging.basicConfig(format="note: %(message)s")

try:
    _Base = make_handler(*from_env())
except ValueError as e:
    _problem = str(e)

    class _Base(BaseHTTPRequestHandler):
        """Settings are missing: say so on every request instead of crashing."""

        def do_GET(self):
            self._fail()

        def do_POST(self):
            self._fail()

        def _fail(self):
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"tax engine webhook: not configured. {_problem}".encode())


class handler(_Base):
    pass
