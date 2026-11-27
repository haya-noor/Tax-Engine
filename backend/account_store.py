"""Which Stripe accounts installed the app, and each one's settings.

Two stores with the same methods:

    MemoryStore     for tests and local runs; forgotten when the process stops
    SupabaseStore   the real one: a Postgres table in Supabase, reached over its REST API

The table is created by supabase/migrations/001_accounts.sql.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

ACTIVE = "active"
UNINSTALLED = "uninstalled"
DEFAULT_COLLECT_IN = ("WA",)    # the states the engine has rules for today


@dataclass
class Account:
    account_id: str                 # the business's Stripe account, acct_...
    status: str = ACTIVE            # active or uninstalled
    livemode: bool = False          # False: installed in a sandbox / test mode
    install_id: str = ""            # Stripe's App Install id, when known
    collect_in: tuple = field(default=DEFAULT_COLLECT_IN)   # states the business collects tax in

    @property
    def active(self):
        return self.status == ACTIVE

    def to_row(self):
        return {"account_id": self.account_id, "status": self.status, "livemode": self.livemode,
                "install_id": self.install_id or None, "collect_in": list(self.collect_in)}

    @classmethod
    def from_row(cls, row):
        return cls(row["account_id"], row.get("status") or ACTIVE, bool(row.get("livemode")),
                   row.get("install_id") or "", tuple(row.get("collect_in") or DEFAULT_COLLECT_IN))


class MemoryStore:
    def __init__(self):
        self.accounts = {}

    def get(self, account_id):
        return self.accounts.get(account_id)

    def installed(self, account_id, livemode=False, install_id=""):
        """Record an install (or reinstall). Keeps the settings of an earlier install."""
        account = self.accounts.get(account_id) or Account(account_id)
        account.status, account.livemode = ACTIVE, livemode
        account.install_id = install_id or account.install_id
        self.accounts[account_id] = account
        return account

    def uninstalled(self, account_id):
        account = self.accounts.get(account_id)
        if account:
            account.status = UNINSTALLED
        return account


class SupabaseError(RuntimeError):
    """Supabase refused a request or could not be reached."""


class SupabaseStore:
    """Accounts in the Supabase table "accounts", through Supabase's REST API (PostgREST).

    Uses the project's service role key, which bypasses row level security, so it
    must only ever live in the server's environment variables, never in the app UI.
    """

    TABLE = "accounts"

    def __init__(self, url, service_key, send=None, timeout=10):
        self.base = url.rstrip("/") + "/rest/v1/" + self.TABLE
        self.headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}",
                        "Content-Type": "application/json"}
        self.timeout = timeout
        self.send = send or self._send     # tests pass a fake

    def _send(self, method, url, headers, body):
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                text = response.read().decode()
        except urllib.error.HTTPError as e:
            raise SupabaseError(f"Supabase {method} failed: {e.code} {e.read().decode()[:200]}") from e
        except urllib.error.URLError as e:
            raise SupabaseError(f"Supabase unreachable: {e.reason}") from e
        return json.loads(text) if text else None

    def _request(self, method, query, body=None, prefer=None):
        headers = dict(self.headers)
        if prefer:
            headers["Prefer"] = prefer
        data = json.dumps(body).encode() if body is not None else None
        return self.send(method, f"{self.base}?{urllib.parse.urlencode(query)}", headers, data)

    def get(self, account_id):
        rows = self._request("GET", {"account_id": f"eq.{account_id}", "select": "*"})
        return Account.from_row(rows[0]) if rows else None

    def installed(self, account_id, livemode=False, install_id=""):
        """Insert the account, or reactivate it keeping its settings (collect_in)."""
        row = {"account_id": account_id, "status": ACTIVE, "livemode": livemode}
        if install_id:
            row["install_id"] = install_id
        rows = self._request("POST", {"on_conflict": "account_id"}, [row],
                             prefer="resolution=merge-duplicates,return=representation")
        return Account.from_row(rows[0]) if rows else Account(account_id, livemode=livemode, install_id=install_id)

    def uninstalled(self, account_id):
        rows = self._request("PATCH", {"account_id": f"eq.{account_id}"}, {"status": UNINSTALLED},
                             prefer="return=representation")
        return Account.from_row(rows[0]) if rows else None
