"""Multi-business backend tests: account stores, the event router, webhook signatures."""

import hashlib
import hmac
import json
import time
import unittest
from pathlib import Path

import stripe

from adapters.stripe_invoice_tax import _WRITTEN
from backend.account_store import Account, MemoryStore, SupabaseStore
from backend.event_router import EventRouter
from stripe_tax_webhook import verify
from taxengine import TaxEngine
from tests.test_stripe_invoice_tax import FakeStripe

FIXTURES = Path(__file__).parent / "fixtures" / "rates"


def seattle_invoice():
    return {"id": "in_1", "status": "draft", "customer_shipping": None,
            "customer_address": {"postal_code": "98101", "state": "WA", "country": "US"}}


class MemoryStoreTest(unittest.TestCase):
    def test_install_uninstall_and_reinstall_keep_settings(self):
        store = MemoryStore()
        store.installed("acct_1", install_id="appinst_1")
        self.assertEqual(store.get("acct_1").collect_in, ("WA",))
        store.get("acct_1").collect_in = ("WA", "OR")
        store.uninstalled("acct_1")
        self.assertFalse(store.get("acct_1").active)
        account = store.installed("acct_1")
        self.assertTrue(account.active)
        self.assertEqual(account.collect_in, ("WA", "OR"))
        self.assertEqual(account.install_id, "appinst_1")


class RouterTest(unittest.TestCase):
    def setUp(self):
        _WRITTEN.clear()        # handle_event remembers what it wrote, across tests too
        self.store = MemoryStore()
        self.clients = {}       # account (None = own) -> FakeStripe

        def factory(key, account=None):
            self.assertTrue(key.startswith("sk_test_"))
            return self.clients.setdefault(account, FakeStripe(seattle_invoice(), [{"id": "il_1", "amount": 10000}]))

        self.router = EventRouter("sk_test_x", TaxEngine(FIXTURES), self.store, client_factory=factory)
        self.router._engines[("WA",)] = TaxEngine(FIXTURES, collect_in={"WA"})

    def invoice_event(self, account=None, livemode=False):
        event = {"type": "invoice.created", "livemode": livemode,
                 "data": {"object": {"id": "in_1", "status": "draft"}}}
        if account:
            event["account"] = account
        return event

    def install(self, account="acct_1", kind="apps.install.created"):
        return self.router.handle({"type": kind, "account": account, "livemode": False,
                                   "data": {"object": {"id": "appinst_1", "object": "apps.install"}}})

    def test_install_then_invoice_is_taxed_for_that_account(self):
        self.assertIn("installed", self.install())
        self.assertEqual(self.store.get("acct_1").install_id, "appinst_1")
        note = self.router.handle(self.invoice_event("acct_1"))
        self.assertTrue(note.startswith("acct_1: in_1: tax"), note)
        self.assertIn("il_1", self.clients["acct_1"].updates)       # written as acct_1, not the platform

    def test_events_from_accounts_without_the_app_are_ignored(self):
        self.assertIn("not installed", self.router.handle(self.invoice_event("acct_2")))
        self.install()
        self.install(kind="apps.install.deleted")
        self.assertIn("not installed", self.router.handle(self.invoice_event("acct_1")))
        self.assertNotIn("acct_1", self.clients)

    def test_older_install_event_names(self):
        self.install(kind="app.install.created")
        self.assertTrue(self.store.get("acct_1").active)
        self.router.handle({"type": "account.application.deauthorized", "account": "acct_1",
                            "data": {"object": {"id": "ca_1", "object": "application"}}})
        self.assertFalse(self.store.get("acct_1").active)

    def test_live_mode_events_are_not_taxed_yet(self):
        self.install()
        self.assertIn("live mode", self.router.handle(self.invoice_event("acct_1", livemode=True)))

    def test_own_account_events_work_as_before(self):
        note = self.router.handle(self.invoice_event())
        self.assertTrue(note.startswith("in_1: tax"), note)
        self.assertIn("il_1", self.clients[None].updates)

    def test_without_a_database_connected_accounts_are_refused(self):
        self.router.store = None
        self.assertIn("no database", self.router.handle(self.invoice_event("acct_1")))
        self.assertIn("no database", self.install())


class SupabaseStoreTest(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.reply = None

        def send(method, url, headers, body):
            self.sent.append((method, url, headers, json.loads(body) if body else None))
            return self.reply

        self.store = SupabaseStore("https://abc.supabase.co/", "service-key", send=send)

    def test_get_reads_one_row(self):
        self.reply = [{"account_id": "acct_1", "status": "active", "livemode": False,
                       "install_id": None, "collect_in": ["WA"]}]
        self.assertEqual(self.store.get("acct_1"), Account("acct_1"))
        method, url, headers, _ = self.sent[0]
        self.assertEqual(method, "GET")
        self.assertEqual(url, "https://abc.supabase.co/rest/v1/accounts?account_id=eq.acct_1&select=%2A")
        self.assertEqual(headers["apikey"], "service-key")
        self.assertNotIn("Authorization", headers)      # new sb_secret_ keys are not JWTs
        self.reply = []
        self.assertIsNone(self.store.get("acct_2"))

    def test_legacy_service_role_jwt_also_goes_in_authorization(self):
        store = SupabaseStore("https://abc.supabase.co", "eyJhbGciOi.legacy", send=lambda *a: [])
        self.assertEqual(store.headers["Authorization"], "Bearer eyJhbGciOi.legacy")

    def test_install_is_an_upsert_that_keeps_settings(self):
        self.reply = [{"account_id": "acct_1", "status": "active", "collect_in": ["WA"]}]
        self.store.installed("acct_1", install_id="appinst_1")
        method, url, headers, body = self.sent[0]
        self.assertEqual(method, "POST")
        self.assertIn("on_conflict=account_id", url)
        self.assertIn("merge-duplicates", headers["Prefer"])
        self.assertEqual(body, [{"account_id": "acct_1", "status": "active", "livemode": False,
                                 "install_id": "appinst_1"}])
        self.assertNotIn("collect_in", body[0])     # a reinstall must not reset the settings

    def test_uninstall_marks_the_row(self):
        self.reply = [{"account_id": "acct_1", "status": "uninstalled"}]
        self.assertFalse(self.store.uninstalled("acct_1").active)
        method, url, _, body = self.sent[0]
        self.assertEqual((method, body), ("PATCH", {"status": "uninstalled"}))


class SignatureTest(unittest.TestCase):
    def sign(self, payload, secret):
        t = int(time.time())
        mac = hmac.new(secret.encode(), f"{t}.{payload}".encode(), hashlib.sha256).hexdigest()
        return f"t={t},v1={mac}"

    def test_accepts_either_endpoint_secret(self):
        payload = json.dumps({"id": "evt_1", "object": "event", "type": "invoice.created", "data": {"object": {}}})
        secrets = ["whsec_own", "whsec_connect"]
        self.assertEqual(verify(payload, self.sign(payload, "whsec_connect"), secrets).id, "evt_1")
        with self.assertRaises(stripe.SignatureVerificationError):
            verify(payload, self.sign(payload, "whsec_other"), secrets)


if __name__ == "__main__":
    unittest.main()
