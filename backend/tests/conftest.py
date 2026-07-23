"""Ensure the synthetic fixture exists before tests run.

The fixture CSV is gitignored (the repo bans *.csv to keep real statements
out), so we regenerate the deterministic synthetic file on demand.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.gen_synthetic import HEADER, _rows

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_phonepe.csv"


@pytest.fixture(scope="session", autouse=True)
def ensure_fixture():
    if not FIXTURE.exists():
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        with FIXTURE.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(HEADER)
            w.writerows(_rows(months=8, seed=42))
    yield
