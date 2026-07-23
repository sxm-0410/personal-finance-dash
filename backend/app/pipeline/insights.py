"""Insights generation (Layer 5b).

Per (cluster x month), compare against the prior month and render plain-language
sentences from templates. Everything is ranked by absolute rupee impact and the
top N kept — an insights feed that lists everything is noise.
"""
from __future__ import annotations

import pandas as pd

INSIGHT_LIMIT = 8


def _fmt(amount: float) -> str:
    return f"₹{amount:,.0f}"


def generate_insights(
    assignments: pd.DataFrame, cluster_labels: dict[int, str]
) -> list[dict]:
    """
    assignments columns: txn_date, amount, cluster_index, counterparty_normalized,
    is_anomaly. Returns list of insight dicts (unranked -> ranked, capped).
    """
    if assignments.empty:
        return []

    df = assignments.copy()
    df["month"] = pd.to_datetime(df["txn_date"]).dt.strftime("%Y-%m")
    insights: list[dict] = []

    for cluster_index, cdf in df.groupby("cluster_index"):
        label = cluster_labels.get(cluster_index, f"Cluster {cluster_index}")
        monthly = cdf.groupby("month")
        totals = monthly["amount"].sum().sort_index()
        months = list(totals.index)

        for i in range(1, len(months)):
            cur, prev = months[i], months[i - 1]
            cur_total, prev_total = totals[cur], totals[prev]
            delta = cur_total - prev_total
            if prev_total > 0 and abs(delta) > 1:
                pct = delta / prev_total * 100
                direction = "grew" if delta > 0 else "shrank"
                sev = "warn" if abs(pct) >= 30 else "info"
                insights.append({
                    "cluster_index": int(cluster_index),
                    "period_month": cur,
                    "kind": "trend",
                    "severity": sev,
                    "impact_amount": round(abs(delta), 2),
                    "body": (
                        f"Your \"{label}\" spending {direction} "
                        f"{abs(pct):.0f}% in {cur} "
                        f"({_fmt(prev_total)} → {_fmt(cur_total)})."
                    ),
                })

            # New merchants appearing this month in this cluster.
            cur_merchants = set(cdf[cdf["month"] == cur]["counterparty_normalized"])
            prev_merchants = set(
                cdf[cdf["month"] <= prev]["counterparty_normalized"]
            )
            new_m = cur_merchants - prev_merchants
            if new_m:
                new_spend = cdf[
                    (cdf["month"] == cur)
                    & (cdf["counterparty_normalized"].isin(new_m))
                ]["amount"].sum()
                sample = ", ".join(sorted(new_m)[:3])
                insights.append({
                    "cluster_index": int(cluster_index),
                    "period_month": cur,
                    "kind": "new_merchant",
                    "severity": "info",
                    "impact_amount": round(float(new_spend), 2),
                    "body": (
                        f"{len(new_m)} new merchant(s) in \"{label}\" this "
                        f"{cur}: {sample}."
                    ),
                })

        # Anomaly summary for the latest month.
        if months:
            latest = months[-1]
            anoms = cdf[(cdf["month"] == latest) & (cdf["is_anomaly"])]
            if not anoms.empty:
                biggest = anoms.loc[anoms["amount"].idxmax()]
                insights.append({
                    "cluster_index": int(cluster_index),
                    "period_month": latest,
                    "kind": "anomaly",
                    "severity": "warn",
                    "impact_amount": round(float(biggest["amount"]), 2),
                    "body": (
                        f"{len(anoms)} unusual transaction(s) in \"{label}\" in "
                        f"{latest}; largest {_fmt(biggest['amount'])} at "
                        f"{biggest['counterparty_normalized']}."
                    ),
                })

    insights.sort(key=lambda x: x["impact_amount"], reverse=True)
    return insights[:INSIGHT_LIMIT]
