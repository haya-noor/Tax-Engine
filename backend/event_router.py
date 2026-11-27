"""Send each Stripe event to the right business.

Once the app is on the Stripe Marketplace, every business that installs it sends
its events to one Connect webhook endpoint. Each such event carries "account":
the business's Stripe account (acct_...). The router then:

- on an install event, records the account (or marks it uninstalled);
- on an invoice event, looks the account up, and if it has the app installed,
  taxes its invoice with the platform key acting for that account
  (the Stripe-Account header) and that account's own settings.

Events without "account" come from the platform's own Stripe account; they are
taxed as before, with the settings from the environment.
"""

import stripe

from adapters.stripe_invoice_tax import handle_event
from taxengine import TaxEngine

# Install events. Stripe renamed them on API version 2026-09-30 (app.install.* before),
# and also sends account.application.* when an account installs or uninstalls an app.
INSTALL_EVENTS = ("apps.install.created", "apps.install.updated",
                  "app.install.created", "app.install.updated", "account.application.authorized")
UNINSTALL_EVENTS = ("apps.install.deleted", "app.install.deleted", "account.application.deauthorized")


class EventRouter:
    def __init__(self, api_key, engine, store=None, resolvers=None, client_factory=None):
        self.api_key = api_key
        self.engine = engine            # for the platform's own account
        self.store = store              # None: no database, so connected accounts are not served
        self.resolvers = resolvers
        self.client_factory = client_factory or (lambda key, account=None: stripe.StripeClient(key, stripe_account=account))
        self.own_client = self.client_factory(api_key)
        self._engines = {}

    def engine_for(self, account):
        """One engine per set of states, built once and reused."""
        key = tuple(sorted(account.collect_in))
        if key not in self._engines:
            self._engines[key] = TaxEngine(collect_in=key, resolvers=self.resolvers)
        return self._engines[key]

    def handle(self, event):
        """Act on one event (a plain dict). Returns a log line, or None if there was nothing to do."""
        kind, account_id = event["type"], event.get("account")
        if kind in INSTALL_EVENTS or kind in UNINSTALL_EVENTS:
            return self._install_change(kind, account_id, event)
        if not account_id:
            return handle_event(self.own_client, self.engine, event)
        if self.store is None:
            return f"{account_id}: {kind} ignored: no database configured (set SUPABASE_URL)"
        account = self.store.get(account_id)
        if not account or not account.active:
            return f"{account_id}: {kind} ignored: the app is not installed"
        if event.get("livemode") or account.livemode:
            return f"{account_id}: {kind} ignored: live mode is not enabled yet"
        note = handle_event(self.client_factory(self.api_key, account_id), self.engine_for(account), event)
        return f"{account_id}: {note}" if note else None

    def _install_change(self, kind, account_id, event):
        if not account_id:
            return None     # the copy Stripe sends to the platform's own endpoints
        if self.store is None:
            return f"{account_id}: {kind} not saved: no database configured (set SUPABASE_URL)"
        if kind in UNINSTALL_EVENTS:
            self.store.uninstalled(account_id)
            return f"{account_id}: app uninstalled"
        obj = event["data"]["object"]
        install_id = obj.get("id", "") if obj.get("object") in ("apps.install", "app.install") else ""
        account = self.store.installed(account_id, bool(event.get("livemode")), install_id)
        return f"{account_id}: app installed, collecting in {', '.join(account.collect_in)}"
