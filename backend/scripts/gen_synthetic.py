"""Generate a synthetic PhonePe-shaped CSV with realistic spending patterns.

Used for tests and end-to-end demos so real financial data never enters the
repo. Emits recurring subscriptions, small-frequent purchases, large one-offs,
weekend discretionary spend, self-transfers, and income — i.e. structure the
clustering should actually discover.

Usage: uv run python -m scripts.gen_synthetic [out.csv] [--months N] [--seed S]
"""
from __future__ import annotations

import argparse
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

HEADER = ["Date", "Time", "Transaction Details", "Type", "Amount", "UTR"]


def _rows(months: int, seed: int) -> list[list[str]]:
    rng = random.Random(seed)
    start = datetime(2024, 1, 1)
    end = start + timedelta(days=30 * months)
    rows: list[list[str]] = []
    utr = 100000

    def add(dt: datetime, details: str, typ: str, amount: float):
        nonlocal utr
        rows.append([
            dt.strftime("%b %d, %Y"),
            dt.strftime("%I:%M %p"),
            details, typ, f"{amount:.2f}", f"UTR{utr}",
        ])
        utr += 1

    # Recurring subscriptions (monthly, stable amount).
    subs = [("Netflix", 649), ("Spotify Premium", 119), ("Jio Recharge", 299)]
    for name, amt in subs:
        d = start + timedelta(days=rng.randint(1, 5))
        while d < end:
            add(d, f"Paid to {name}", "DEBIT", amt + rng.uniform(-1, 1))
            d += timedelta(days=30 + rng.randint(-1, 1))

    # Small frequent purchases (tea/coffee/snacks, many times).
    small = ["Chai Point", "Cafe Coffee Day", "Local Kirana", "Amul Parlour"]
    d = start
    while d < end:
        if rng.random() < 0.7:
            add(d + timedelta(hours=rng.randint(8, 20)),
                f"Paid to {rng.choice(small)}", "DEBIT",
                rng.uniform(20, 120))
        d += timedelta(days=1)

    # Weekend discretionary (restaurants, movies) on Sat/Sun.
    weekend = ["Swiggy Order", "Zomato Order", "PVR Cinemas", "BookMyShow"]
    d = start
    while d < end:
        if d.weekday() >= 5 and rng.random() < 0.6:
            add(d + timedelta(hours=rng.randint(12, 22)),
                f"Paid to {rng.choice(weekend)}", "DEBIT",
                rng.uniform(300, 900))
        d += timedelta(days=1)

    # Large one-offs (electronics, travel).
    big = ["Amazon Order", "Flipkart Order", "MakeMyTrip", "Croma Electronics"]
    for _ in range(months * 2):
        dt = start + timedelta(days=rng.randint(0, 30 * months))
        add(dt, f"Paid to {rng.choice(big)}", "DEBIT", rng.uniform(4000, 25000))

    # A couple of anomalies (huge amount for a normally-small merchant).
    add(start + timedelta(days=45), "Paid to Chai Point", "DEBIT", 3500)

    # Self-transfers (equal debit + credit within a day).
    for _ in range(months):
        dt = start + timedelta(days=rng.randint(0, 30 * months))
        amt = rng.choice([5000, 10000, 15000])
        add(dt, "Paid to Self Account", "DEBIT", amt)
        add(dt + timedelta(hours=2), "Received from Self Account", "CREDIT", amt)

    # Income (monthly salary credit).
    d = start + timedelta(days=1)
    while d < end:
        add(d, "Received from ACME Corp Payroll", "CREDIT", 65000)
        d += timedelta(days=30)

    rows.sort(key=lambda r: datetime.strptime(f"{r[0]} {r[1]}", "%b %d, %Y %I:%M %p"))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="tests/fixtures/synthetic_phonepe.csv")
    ap.add_argument("--months", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = _rows(args.months, args.seed)
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        w.writerows(rows)
    print(f"Wrote {len(rows)} transactions to {out}")


if __name__ == "__main__":
    main()
