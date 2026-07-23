"""Reconciliation harness — score the PDF parser against the CSV oracle.

You have both a PDF and a CSV export of the same period. The CSV parses
reliably, so treat it as ground truth and measure how well the PDF adapter
recovers the same transactions. Matches on the multiset of
(date, amount, direction) — reference IDs aren't always present in the PDF.

Usage:
    uv run python -m scripts.reconcile <statement.pdf> <statement.csv> [--password PW]

Prints matched %, PDF-only rows (false positives) and CSV-only rows (misses).
This is PRD Success Metric #3 turned into a number.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from app.pipeline.adapters.phonepe_csv import PhonePeCSVAdapter
from app.pipeline.adapters.phonepe_pdf import PhonePePDFAdapter


def _key(txn) -> tuple:
    return (txn["txn_date"].date(), round(float(txn["amount"]), 2), txn["direction"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--password", default=None)
    args = ap.parse_args()

    csv_res = PhonePeCSVAdapter().parse(args.csv)
    pdf_res = PhonePePDFAdapter().parse(args.pdf, args.password)

    truth = Counter(_key(t) for t in csv_res.rows)
    got = Counter(_key(t) for t in pdf_res.rows)

    matched = sum((truth & got).values())
    misses = truth - got          # in CSV, missing from PDF
    false_pos = got - truth       # in PDF, not in CSV

    total_truth = sum(truth.values())
    rate = matched / total_truth if total_truth else 0.0

    print(f"CSV (truth) transactions : {total_truth}")
    print(f"PDF parsed transactions  : {sum(got.values())}")
    print(f"PDF unparsed rows        : {len(pdf_res.unparsed)}")
    print(f"Matched                  : {matched}")
    print(f"Match rate               : {rate:.1%}")
    print(f"Misses (CSV-only)        : {sum(misses.values())}")
    print(f"False positives (PDF-only): {sum(false_pos.values())}")

    if misses:
        print("\nSample misses:")
        for k, n in list(misses.items())[:10]:
            print(f"  {k} x{n}")
    if rate >= 0.90:
        print("\n✓ Meets the >90% parse-rate success metric.")
    else:
        print("\n✗ Below 90% — inspect the samples above and the unparsed queue.")


if __name__ == "__main__":
    main()
