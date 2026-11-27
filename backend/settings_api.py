"""The app's settings screen in the Stripe Dashboard talks to these two endpoints.

    POST /settings/get    -> {"collect_in": ["WA"], "supported_states": ["WA"]}
    POST /settings/save   {"collect_in": ["WA"]} -> the saved settings

The screen (stripe-app/src/views/AppSettings.tsx) signs each request with
fetchStripeSignature(); Stripe signs the JSON {...payload, user_id, account_id}
with the app's signing secret (absec_..., STRIPE_APP_SECRET). We rebuild that
exact JSON from the body and check the signature, so only the Stripe account
that the Dashboard user is signed in to can read or change its own settings.

Docs: https://docs.stripe.com/stripe-apps/build-backend
"""

import json

import stripe

from taxengine import taxability_files

SETTINGS_PATHS = ("/settings/get", "/settings/save")


def supported_states():
    """States the engine has product rules for (taxengine/states/)."""
    return sorted(taxability_files())


def signed_payload(fields, body):
    """The JSON string the Dashboard signed: the extra fields in order, then user_id and account_id."""
    data = {k: body[k] for k in fields}
    data["user_id"] = body["user_id"]
    data["account_id"] = body["account_id"]
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def handle_settings(path, raw_body, signature, store, app_secret):
    """(HTTP status, JSON-able reply) for a settings request."""
    if store is None or not app_secret:
        return 503, {"error": "settings are not configured on the server"}
    try:
        body = json.loads(raw_body or b"{}")
        fields = ("collect_in",) if path == "/settings/save" else ()
        stripe.WebhookSignature.verify_header(signed_payload(fields, body), signature or "", app_secret)
    except (ValueError, KeyError, TypeError, stripe.SignatureVerificationError):
        return 401, {"error": "invalid signature"}

    account_id = body["account_id"]
    account = store.get(account_id)
    if not account or not account.active:
        return 404, {"error": "the app is not installed on this account"}
    if path == "/settings/save":
        states = body["collect_in"]
        if not isinstance(states, list) or any(s not in supported_states() for s in states):
            return 400, {"error": f"collect_in must be a list of: {', '.join(supported_states())}"}
        account = store.set_collect_in(account_id, sorted(set(states)))
    return 200, {"collect_in": list(account.collect_in), "supported_states": supported_states()}
