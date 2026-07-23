"""Cluster labeling (Layer 5a).

Rule-based, deterministic, explainable. We rank each centroid's features into
low/mid/high percentile buckets (across clusters) and match an ordered rule
table. The numeric centroid_summary always ships alongside the label so the UI
can show the evidence: "avg ₹340 · 12x/mo · 78% recurring".
"""
from __future__ import annotations

import numpy as np

from app.models import CLUSTERING_COLUMNS

# indices into the clustering feature vector (centroids come in this order)
_I = {name: i for i, name in enumerate(CLUSTERING_COLUMNS)}


def _buckets(centroids: np.ndarray) -> np.ndarray:
    """Return low/mid/high (0/1/2) per feature, ranked across clusters."""
    out = np.zeros_like(centroids, dtype=int)
    for j in range(centroids.shape[1]):
        col = centroids[:, j]
        if np.ptp(col) < 1e-9:
            out[:, j] = 1
            continue
        lo, hi = np.percentile(col, [33, 66])
        out[:, j] = np.where(col <= lo, 0, np.where(col >= hi, 2, 1))
    return out


def _summary(centroid: np.ndarray) -> dict:
    log_amt = centroid[_I["log_amount"]]
    return {
        "avg_amount": round(float(np.expm1(log_amt)), 2),
        "merchant_frequency": round(float(np.expm1(centroid[_I["merchant_frequency"]])), 1),
        "recurring_share": round(float(centroid[_I["is_recurring"]]), 2),
        "amount_stability": round(float(centroid[_I["amount_stability"]]), 2),
    }


def label_clusters(centroids_original: np.ndarray) -> list[dict]:
    """One dict per cluster: {label, centroid_summary}."""
    b = _buckets(centroids_original)
    results = []
    for i in range(centroids_original.shape[0]):
        row = b[i]
        recurring = row[_I["is_recurring"]]
        stability = row[_I["amount_stability"]]
        frequency = row[_I["merchant_frequency"]]
        # Absolute average rupee value of the cluster (not a relative bucket) so
        # "big-ticket" only ever means genuinely large, never just "highest of
        # three small clusters".
        avg = float(np.expm1(centroids_original[i][_I["log_amount"]]))
        big = avg >= 1500
        small = avg <= 150

        # Lead with the dimensions that actually separate a personal dataset:
        # recurring, then frequency, then stability; amount only refines.
        if recurring == 2:
            label = "Recurring bills & subscriptions"
        elif frequency == 2:
            label = "Frequent big-ticket spending" if big else "Frequent everyday spending"
        elif big:
            label = "Large one-off purchases"
        elif stability == 2 and frequency <= 1:
            label = "One-off & occasional spending"
        elif small:
            label = "Small everyday spend"
        else:
            label = "Mid-size regular spend"

        results.append(
            {"label": label, "centroid_summary": _summary(centroids_original[i])}
        )

    # Disambiguate duplicate labels with a numeric suffix.
    seen: dict[str, int] = {}
    for r in results:
        base = r["label"]
        if base in seen:
            seen[base] += 1
            r["label"] = f"{base} ({seen[base]})"
        else:
            seen[base] = 1
    return results
