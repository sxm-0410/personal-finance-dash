"""Cleaning & normalization (Layer 2).

Takes RawTransactions from an adapter and produces a cleaned pandas DataFrame
ready for persistence. Responsibilities:
  - deterministic dedup key (idempotent ingest across PDF/CSV overlap)
  - self-transfer / income / refund classification (txn_kind)
  - three-tier merchant normalization
  - privacy pass: hash references, mask UPI ids

Nothing is deleted — self-transfers are tagged, not dropped, so totals can
exclude them while the table still shows them.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pandas as pd
import yaml
from rapidfuzz import fuzz, process

from app.pipeline.adapters.base import RawTransaction

# ── Privacy ────────────────────────────────────────────────────────────────
_UPI_ID = re.compile(r"([a-zA-Z0-9._-]{2,})(@[a-zA-Z]+)")


def _hash_reference(ref: str | None) -> str | None:
    if not ref:
        return None
    return hashlib.sha256(ref.encode()).hexdigest()[:16]


def _mask_upi(text: str) -> str:
    def repl(m: re.Match) -> str:
        handle, suffix = m.group(1), m.group(2)
        return f"{handle[:3]}***{suffix}" if len(handle) > 3 else f"***{suffix}"
    return _UPI_ID.sub(repl, text)


def dedup_key(txn: RawTransaction) -> str:
    """Prefer UTR; else compose from date+amount+counterparty."""
    if txn["reference_id"]:
        base = f"ref:{txn['reference_id']}"
    else:
        base = (
            f"{txn['txn_date'].date()}|{txn['amount']}|"
            f"{txn['direction']}|{txn['counterparty_raw'][:40].lower()}"
        )
    return hashlib.sha256(base.encode()).hexdigest()[:32]


# ── Merchant normalization (3 tiers) ────────────────────────────────────────
_UPI_SUFFIX = re.compile(r"@[a-zA-Z]+")
_TRAILING_CODE = re.compile(r"[\s\-_]*\d{4,}$")
_NOISE = re.compile(r"\b(pvt|ltd|limited|india|payment|upi|txn|ref|order)\b", re.I)
_TXN_PREFIX = re.compile(
    r"^\s*(paid to|received from|payment to|sent to|money sent to|"
    r"money received from|to|from)\s+",
    re.I,
)


def _scrub(name: str) -> str:
    n = _mask_upi(name)
    n = _TXN_PREFIX.sub("", n)
    n = _UPI_SUFFIX.sub("", n)
    n = _TRAILING_CODE.sub("", n)
    n = _NOISE.sub("", n)
    n = re.sub(r"[^\w\s&]", " ", n)
    n = re.sub(r"\s+", " ", n).strip().upper()
    return n or "UNKNOWN"


def _load_overrides() -> dict[str, str]:
    path = Path(__file__).resolve().parent.parent.parent / "merchant_overrides.yaml"
    if not path.exists():
        return {}
    with path.open() as fh:
        data = yaml.safe_load(fh) or {}
    return {k.upper(): v for k, v in data.items()}


def _fuzzy_canonicalize(names: pd.Series, threshold: int = 88) -> dict[str, str]:
    """Group near-identical scrubbed names; canonical = most frequent variant."""
    counts = names.value_counts()
    unique = list(counts.index)
    canonical: dict[str, str] = {}
    assigned: set[str] = set()
    for name in unique:  # already sorted by frequency desc
        if name in assigned:
            continue
        canonical[name] = name
        assigned.add(name)
        matches = process.extract(
            name, unique, scorer=fuzz.token_set_ratio, limit=None
        )
        for cand, score, _ in matches:
            if cand not in assigned and score >= threshold:
                canonical[cand] = name
                assigned.add(cand)
    return canonical


def normalize_merchants(scrubbed: pd.Series, threshold: int = 88) -> pd.Series:
    overrides = _load_overrides()
    canon_map = _fuzzy_canonicalize(scrubbed, threshold)

    def apply(name: str) -> str:
        grouped = canon_map.get(name, name)
        return overrides.get(grouped.upper(), grouped)  # override wins last

    return scrubbed.map(apply)


# ── Self-transfer / kind classification ─────────────────────────────────────
def classify_kinds(df: pd.DataFrame, owner_terms: list[str]) -> pd.Series:
    kinds = pd.Series("spend", index=df.index)
    owner_pat = "|".join(re.escape(t.upper()) for t in owner_terms if t)

    # income = credits that aren't refunds
    kinds[df["direction"] == "credit"] = "income"
    refund_mask = (df["direction"] == "credit") & df[
        "counterparty_raw"
    ].str.contains("refund", case=False, na=False)
    kinds[refund_mask] = "refund"

    # self-transfer: counterparty matches an owner term (either direction)
    if owner_pat:
        self_mask = df["counterparty_normalized"].str.contains(
            owner_pat, case=False, na=False, regex=True
        )
        kinds[self_mask] = "self_transfer"

    # self-transfer heuristic: equal-amount debit/credit within 2 days
    df_sorted = df.sort_values("txn_date")
    for amt, grp in df_sorted.groupby(df_sorted["amount"].round(2)):
        if len(grp) < 2:
            continue
        debits = grp[grp["direction"] == "debit"]
        credits = grp[grp["direction"] == "credit"]
        for di, drow in debits.iterrows():
            near = credits[
                (credits["txn_date"] - drow["txn_date"]).abs()
                <= pd.Timedelta(days=2)
            ]
            if not near.empty:
                kinds[di] = "self_transfer"
                kinds[near.index[0]] = "self_transfer"
    return kinds


def clean(
    rows: list[RawTransaction],
    owner_terms: list[str] | None = None,
    fuzzy_threshold: int = 88,
) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    owner_terms = owner_terms or []

    df = pd.DataFrame(rows)
    df["amount"] = df["amount"].astype(float)
    df["txn_date"] = pd.to_datetime(df["txn_date"])
    df["dedup_key"] = [dedup_key(r) for r in rows]
    df["reference_hash"] = df["reference_id"].map(_hash_reference)

    scrubbed = df["counterparty_raw"].map(_scrub)
    df["counterparty_normalized"] = normalize_merchants(scrubbed, fuzzy_threshold)
    df["counterparty_raw"] = df["counterparty_raw"].map(_mask_upi)

    df["txn_kind"] = classify_kinds(df, owner_terms)

    # Idempotency: drop within-batch duplicates by dedup_key.
    df = df.drop_duplicates(subset="dedup_key").reset_index(drop=True)
    return df
