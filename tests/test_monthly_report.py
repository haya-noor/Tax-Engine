"""Monthly report from invoice records (adapters/stripe_monthly_report.py)."""

import csv
import os
import tempfile
import unittest

from adapters.stripe_monthly_report import build_report, format_report, month_range, write_csv

NOV_START, NOV_END = month_range(2026, 11)


def invoice(id_, status="paid", when=NOV_START + 3600, **record):
    meta = {"tax_engine_" + k: str(v) for k, v in record.items()}
    return {"id": id_, "status": status, "status_transitions": {"finalized_at": when}, "metadata": meta}


BELLEVUE = dict(state="WA", location="1704", jurisdiction="BELLEVUE RTA (1704)")


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.invoices = [
            invoice("in_1", **BELLEVUE, gross_cents=6200, taxable_cents=6200, state_tax_cents=403, local_tax_cents=236),
            invoice("in_2", status="open", **BELLEVUE, gross_cents=1000, taxable_cents=500,
                    state_tax_cents=33, local_tax_cents=19),
            invoice("in_3", state="WA", location="1726", jurisdiction="SEATTLE (1726)", gross_cents=10000,
                    taxable_cents=10000, state_tax_cents=650, local_tax_cents=405),
            invoice("in_void", status="void", **BELLEVUE, gross_cents=999, taxable_cents=999,
                    state_tax_cents=1, local_tax_cents=1),
            invoice("in_draft", status="draft", when=None, **BELLEVUE, gross_cents=1, taxable_cents=1,
                    state_tax_cents=1, local_tax_cents=1),
            invoice("in_oct", when=NOV_START - 10, **BELLEVUE, gross_cents=1, taxable_cents=1,
                    state_tax_cents=1, local_tax_cents=1),
            invoice("in_or", state="OR", location="", jurisdiction="PORTLAND", gross_cents=500, taxable_cents=0,
                    state_tax_cents=0, local_tax_cents=0),
            {"id": "in_old", "status": "paid", "status_transitions": {"finalized_at": NOV_START + 5}, "metadata": {}},
        ]

    def test_totals_per_location(self):
        report = build_report(self.invoices, 2026, 11, state="WA")
        rows = {r.location: r for r in report.rows}
        self.assertEqual(set(rows), {"1704", "1726"})
        bellevue = rows["1704"]
        self.assertEqual((bellevue.invoices, bellevue.gross_cents, bellevue.taxable_cents), (2, 7200, 6700))
        self.assertEqual((bellevue.state_tax_cents, bellevue.local_tax_cents), (436, 255))
        self.assertEqual(report.untracked, ["in_old"])

    def test_all_states(self):
        report = build_report(self.invoices, 2026, 11)
        self.assertEqual([r.state for r in report.rows], ["OR", "WA", "WA"])

    def test_outputs(self):
        report = build_report(self.invoices, 2026, 11, state="WA")
        text = format_report(report)
        self.assertIn("BELLEVUE RTA (1704)", text)
        self.assertIn("in_old", text)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nov.csv")
            write_csv(report, path)
            with open(path, newline="") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]["location_code"], "1704")
        self.assertEqual(rows[0]["total_tax"], "6.91")


if __name__ == "__main__":
    unittest.main()
