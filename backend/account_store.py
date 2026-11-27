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
                   row.get("install_id") or "",
                   DEFAULT_COLLECT_IN if row.get("collect_in") is None else tuple(row["collect_in"]))


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

    def set_collect_in(self, account_id, states):
        account = self.accounts.get(account_id)
        if account:
            account.collect_in = tuple(states)
        return account


class SupabaseError(RuntimeError):
    """Supabase refused a request or could not be reached."""


class SupabaseStore:
    """Accounts in the Supabase table "accounts", through Supabase's REST API (PostgREST).

    Uses the project's secret key (sb_secret_..., or the legacy service_role JWT),
    which acts as the service_role and bypasses row level security, so it must only
    ever live in the server's environment variables, never in the app UI.
    """

    TABLE = "accounts"

    def __init__(self, url, service_key, send=None, timeout=10):
        # SUPABASE_URL is the project URL (https://<ref>.supabase.co). Supabase also shows
        # the REST endpoint (.../rest/v1); accept that too instead of doubling the path.
        url = url.strip().rstrip("/")
        url = url[: -len("/rest/v1")] if url.endswith("/rest/v1") else url
        self.base = url + "/rest/v1/" + self.TABLE
        self.headers = {"apikey": service_key, "Content-Type": "application/json"}
        if service_key.startswith("eyJ"):
            # Legacy service_role keys are JWTs and also go in Authorization. New
            # sb_secret_ keys are not JWTs and must only be sent as apikey.
            self.headers["Authorization"] = f"Bearer {service_key}"
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

    def set_collect_in(self, account_id, states):
        rows = self._request("PATCH", {"account_id": f"eq.{account_id}"}, {"collect_in": list(states)},
                             prefer="return=representation")
        return Account.from_row(rows[0]) if rows else None
