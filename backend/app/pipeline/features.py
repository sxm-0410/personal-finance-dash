"""Feature engineering (Layer 3).

Seven features, each individually defensible (see the plan's feature table).
Computed only on spendable transactions — self-transfers and income are
excluded from the clustering matrix but stay in the DB.

Recurring detection runs here (it's an INPUT to clustering, not an output):
for each merchant with >=3 txns, if the coefficient of variation of the
inter-arrival gaps is low AND the mean gap sits near 7/30/365 days, it's
flagged recurring.
"""
from __future__ import annotations

import calendar

import numpy as np
import pandas as pd

RECURRING_PERIODS = (7, 30, 365)
RECURRING_CV_MAX = 0.25
RECURRING_TOL = 0.30  # mean gap within +/-30% of a period


def _is_recurring_merchant(dates: pd.Series) -> bool:
    if len(dates) < 3:
        return False
    gaps = dates.sort_values().diff().dropna().dt.days.to_numpy()
    gaps = gaps[gaps > 0]
    if len(gaps) < 2:
        return False
    mean_gap = gaps.mean()
    if mean_gap == 0:
        return False
    cv = gaps.std() / mean_gap
    if cv > RECURRING_CV_MAX:
        return False
    return any(abs(mean_gap - p) <= RECURRING_TOL * p for p in RECURRING_PERIODS)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return a features DataFrame with one row per spend transaction.

    `df` must carry a unique 'id' column; the output's 'transaction_id' echoes
    it so the caller can align features back to the source rows. Rows come out
    sorted by txn_date (recency needs ordering).
    """
    spend = df[df["txn_kind"] == "spend"].copy()
    if spend.empty:
        return pd.DataFrame()

    spend = spend.sort_values("txn_date").reset_index(drop=True)
    spend["transaction_id"] = spend["id"]

    dt = spend["txn_date"]
    dow = dt.dt.dayofweek
    spend["log_amount"] = np.log1p(spend["amount"])
    spend["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    spend["dow_cos"] = np.cos(2 * np.pi * dow / 7)
    days_in_month = dt.dt.days_in_month
    spend["day_of_month_norm"] = dt.dt.day / days_in_month

    # Per-merchant aggregates.
    grp = spend.groupby("counterparty_normalized")
    freq = grp["amount"].transform("count")
    spend["merchant_frequency"] = np.log1p(freq)

    # Recency: days since previous txn at the same merchant.
    spend["recency_days"] = (
        grp["txn_date"].diff().dt.days.fillna(9999).clip(upper=9999)
    )
    # Normalize recency to a soft 0..1 (log scale) so it doesn't dominate.
    spend["recency_days"] = np.log1p(spend["recency_days"]) / np.log1p(9999)

    # Amount stability: 1 - coefficient of variation per merchant (clipped).
    def _stability(s: pd.Series) -> pd.Series:
        m = s.mean()
        cv = (s.std(ddof=0) / m) if m else 0.0
        return pd.Series(np.clip(1 - cv, 0, 1), index=s.index)

    spend["amount_stability"] = grp["amount"].transform(
        lambda s: np.clip(1 - (s.std(ddof=0) / s.mean() if s.mean() else 0), 0, 1)
    )

    # Recurring flag per merchant.
    recurring_map = grp["txn_date"].apply(_is_recurring_merchant)
    spend["is_recurring"] = (
        spend["counterparty_normalized"].map(recurring_map).astype(float)
    )

    cols = [
        "transaction_id",
        "log_amount",
        "dow_sin",
        "dow_cos",
        "day_of_month_norm",
        "merchant_frequency",
        "recency_days",
        "is_recurring",
        "amount_stability",
    ]
    return spend[cols].reset_index(drop=True)


def days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]
