"""Monthly sales tax report from Stripe invoices.

Every invoice the engine taxes carries a small record in its metadata (see
record_for() in stripe_invoice_tax.py): the state, the DOR location code, the gross
and taxable amounts, and the state and local tax. This module adds those up for
one month, per location, which is what Washington's excise tax return asks for:
the state part on the total, and the local part per location code.

An invoice counts in the month it was finalized (sent or charged), which is when
the sale is reported. Drafts and voided invoices are left out.
"""

import calendar
import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .stripe_invoice_tax import RECORD_PREFIX, plain

REPORTED = {"open", "paid", "uncollectible"}     # finalized; "void" and "draft" are not sales


@dataclass
class LocationTotal:
    state: str
    location: str           # DOR location code, or "" when the rate came from the ZIP table
    jurisdiction: str
    invoices: int = 0
    gross_cents: int = 0
    taxable_cents: int = 0
    state_tax_cents: int = 0
    local_tax_cents: int = 0


@dataclass
class MonthlyReport:
    year: int
    month: int
    rows: list = field(default_factory=list)          # LocationTotal, sorted by state and location
    untracked: list = field(default_factory=list)     # ids of finalized invoices without our record


def month_range(year, month):
    """(start, end) of the month as Unix timestamps, UTC."""
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    days = calendar.monthrange(year, month)[1]
    end = start.replace(day=days, hour=23, minute=59, second=59)
    return int(start.timestamp()), int(end.timestamp()) + 1


def finalized_at(invoice):
    return ((invoice.get("status_transitions") or {}).get("finalized_at")) or None


def build_report(invoices, year, month, state=None):
    """Add up the invoices finalized in the month. invoices: dicts or Stripe objects."""
    start, end = month_range(year, month)
    totals, untracked = {}, []
    for inv in map(plain, invoices):
        when = finalized_at(inv)
        if inv.get("status") not in REPORTED or not when or not (start <= when < end):
            continue
        meta = {k[len(RECORD_PREFIX):]: v for k, v in (inv.get("metadata") or {}).items()
                if k.startswith(RECORD_PREFIX)}
        if not meta:
            untracked.append(inv["id"])
            continue
        if state and meta.get("state", "").upper() != state.upper():
            continue
        key = (meta.get("state", ""), meta.get("location", ""), meta.get("jurisdiction", ""))
        row = totals.setdefault(key, LocationTotal(*key))
        row.invoices += 1
        row.gross_cents += int(meta.get("gross_cents", 0))
        row.taxable_cents += int(meta.get("taxable_cents", 0))
        row.state_tax_cents += int(meta.get("state_tax_cents", 0))
        row.local_tax_cents += int(meta.get("local_tax_cents", 0))
    rows = sorted(totals.values(), key=lambda r: (r.state, r.location, r.jurisdiction))
    return MonthlyReport(year, month, rows, untracked)


def fetch_invoices(client, year, month):
    """Invoices that could have been finalized in the month (created up to 60 days before it)."""
    start, end = month_range(year, month)
    params = {"created": {"gte": start - 60 * 86400, "lt": end}, "limit": 100}
    return client.v1.invoices.list(params).auto_paging_iter()


COLUMNS = ["state", "location_code", "location", "invoices", "gross_sales", "taxable_sales",
           "state_tax", "local_tax", "total_tax"]


def dollars(cents):
    return f"{cents / 100:.2f}"


def write_csv(report, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r in report.rows:
            w.writerow([r.state, r.location, r.jurisdiction, r.invoices, dollars(r.gross_cents),
                        dollars(r.taxable_cents), dollars(r.state_tax_cents), dollars(r.local_tax_cents),
                        dollars(r.state_tax_cents + r.local_tax_cents)])


def format_report(report):
    out = [f"Sales tax report for {report.year}-{report.month:02d}", ""]
    out.append(f"{'Code':<6}{'Location':<28}{'Inv':>4}{'Gross':>12}{'Taxable':>12}{'State tax':>11}{'Local tax':>11}")
    for r in report.rows:
        name = (r.jurisdiction or "-")[:27]
        out.append(f"{r.location or '-':<6}{name:<28}{r.invoices:>4}{dollars(r.gross_cents):>12}"
                   f"{dollars(r.taxable_cents):>12}{dollars(r.state_tax_cents):>11}{dollars(r.local_tax_cents):>11}")
    t = lambda attr: sum(getattr(r, attr) for r in report.rows)
    out.append(f"{'':<6}{'TOTAL':<28}{t('invoices'):>4}{dollars(t('gross_cents')):>12}"
               f"{dollars(t('taxable_cents')):>12}{dollars(t('state_tax_cents')):>11}{dollars(t('local_tax_cents')):>11}")
    if any(not r.location for r in report.rows):
        out.append("\nRows without a location code were taxed by ZIP code only (no street address);"
                   " check their location before filing.")
    if report.untracked:
        out.append(f"\n{len(report.untracked)} finalized invoice(s) have no tax record from this engine"
                   f" (taxed before the record existed, or not by this engine): {', '.join(report.untracked[:10])}")
    return "\n".join(out)
