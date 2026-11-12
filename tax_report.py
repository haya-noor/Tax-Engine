"""Monthly sales tax report from your Stripe invoices, per location code.

    $env:STRIPE_SECRET_KEY = "sk_test_..."
    python tax_report.py 2026-11                 # prints the table
    python tax_report.py 2026-11 --csv nov.csv   # also saves a CSV

It adds up the invoices finalized in that month that this engine taxed: gross
and taxable sales, state tax and local tax, per Washington location code. These
are the figures for the state's excise tax return. Check them before filing.
"""

import argparse
import os
import sys

import stripe

from adapters.stripe_report import build_report, fetch_invoices, format_report, write_csv


def main():
    parser = argparse.ArgumentParser(description="Monthly sales tax report from Stripe invoices")
    parser.add_argument("month", help="YYYY-MM, e.g. 2026-11")
    parser.add_argument("--state", default="WA", help="only this state (default WA); 'all' for every state")
    parser.add_argument("--csv", help="also save the report to this CSV file")
    args = parser.parse_args()

    try:
        year, month = (int(x) for x in args.month.split("-"))
    except ValueError:
        sys.exit("Month must look like 2026-11")
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key.startswith(("sk_", "rk_")):
        sys.exit("Set STRIPE_SECRET_KEY first.")
    client = stripe.StripeClient(key)

    state = None if args.state.lower() == "all" else args.state
    report = build_report(fetch_invoices(client, year, month), year, month, state)
    print(format_report(report))
    if args.csv:
        write_csv(report, args.csv)
        print(f"\nSaved {args.csv}")


if __name__ == "__main__":
    main()
