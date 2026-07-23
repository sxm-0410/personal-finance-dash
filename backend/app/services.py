"""Orchestration: wire the pipeline modules to the database.

Two entry points:
  ingest_file  — parse -> clean -> idempotent upsert of transactions + unparsed
  recluster    — features -> cluster -> label -> insights, all under a new run

Kept out of the routers so it's testable and callable from scripts.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Cluster,
    ClusterAssignment,
    Feature,
    Insight,
    Run,
    Transaction,
    UnparsedRow,
)
from app.pipeline.adapters import parse_file
from app.pipeline.clean import clean
from app.pipeline.cluster import run_clustering
from app.pipeline.features import build_features
from app.pipeline.insights import generate_insights
from app.pipeline.label import label_clusters

OWNER_TERMS = ["self", "own account", "my account"]


def latest_run_id(db: Session) -> str | None:
    row = db.execute(
        select(Run.id).order_by(Run.created_at.desc()).limit(1)
    ).first()
    return row[0] if row else None


def ingest_file(db: Session, path: Path, password: str | None = None) -> dict:
    result = parse_file(path, password)
    df = clean(result.rows, owner_terms=OWNER_TERMS,
               fuzzy_threshold=settings.fuzzy_threshold)

    existing = {k for (k,) in db.execute(select(Transaction.dedup_key)).all()}
    inserted = 0
    for _, row in df.iterrows():
        if row["dedup_key"] in existing:
            continue
        db.add(Transaction(
            txn_date=row["txn_date"].to_pydatetime(),
            amount=float(row["amount"]),
            direction=row["direction"],
            txn_kind=row["txn_kind"],
            counterparty_raw=row["counterparty_raw"],
            counterparty_normalized=row["counterparty_normalized"],
            reference_hash=row["reference_hash"],
            dedup_key=row["dedup_key"],
            source_app=row["source_app"],
            parse_confidence=float(row["parse_confidence"]),
        ))
        existing.add(row["dedup_key"])
        inserted += 1

    for u in result.unparsed:
        db.add(UnparsedRow(source_file=result.source_file,
                           raw_line=u.raw_line, reason=u.reason))
    db.commit()

    stats = result.stats()
    stats["inserted"] = inserted
    stats["duplicates_skipped"] = len(df) - inserted
    return stats


def _load_spend_df(db: Session) -> pd.DataFrame:
    txns = db.execute(
        select(Transaction).where(Transaction.txn_kind == "spend")
    ).scalars().all()
    if not txns:
        return pd.DataFrame()
    return pd.DataFrame([{
        "id": t.id,
        "txn_date": pd.Timestamp(t.txn_date),
        "amount": float(t.amount),
        "direction": t.direction,
        "txn_kind": t.txn_kind,
        "counterparty_normalized": t.counterparty_normalized,
    } for t in txns])


def recluster(db: Session) -> dict:
    spend = _load_spend_df(db)
    if len(spend) < settings.k_min + 1:
        raise ValueError("Not enough spend transactions to cluster")

    # build_features returns rows sorted by txn_date with a 'transaction_id'
    # echoing the DB id. Align spend to that exact order so every array (labels,
    # distances, pca, anomalies) indexes the same row.
    features = build_features(spend)
    spend_sorted = (
        spend.set_index("id")
        .loc[features["transaction_id"]]
        .reset_index()
        .rename(columns={"index": "id"})
    )

    result = run_clustering(features, spend_sorted)

    # Persist features.
    db.query(Feature).delete()
    for i, fid in enumerate(features["transaction_id"]):
        db.add(Feature(
            transaction_id=fid,
            log_amount=float(features.loc[i, "log_amount"]),
            dow_sin=float(features.loc[i, "dow_sin"]),
            dow_cos=float(features.loc[i, "dow_cos"]),
            day_of_month_norm=float(features.loc[i, "day_of_month_norm"]),
            merchant_frequency=float(features.loc[i, "merchant_frequency"]),
            recency_days=float(features.loc[i, "recency_days"]),
            is_recurring=float(features.loc[i, "is_recurring"]),
            amount_stability=float(features.loc[i, "amount_stability"]),
        ))

    run = Run(
        algo="kmeans+dbscan",
        k=result.k,
        silhouette=result.silhouette,
        mean_ari=result.mean_ari,
        n_transactions=len(spend_sorted),
        metrics_json=result.metrics,
        scaler_blob=result.scaler_blob,
    )
    db.add(run)
    db.flush()

    labels = label_clusters(result.centroids_original)
    clusters_by_index: dict[int, Cluster] = {}
    for idx in range(result.k):
        mask = result.labels == idx
        total = float(spend_sorted.loc[mask, "amount"].sum())
        c = Cluster(
            run_id=run.id,
            cluster_index=idx,
            label=labels[idx]["label"],
            centroid_summary=labels[idx]["centroid_summary"],
            n_transactions=int(mask.sum()),
            total_amount=total,
        )
        db.add(c)
        db.flush()
        clusters_by_index[idx] = c

    for i in range(len(spend_sorted)):
        idx = int(result.labels[i])
        db.add(ClusterAssignment(
            transaction_id=spend_sorted.loc[i, "id"],
            cluster_id=clusters_by_index[idx].id,
            run_id=run.id,
            distance_to_centroid=float(result.distances[i]),
            pca_x=float(result.pca_coords[i, 0]),
            pca_y=float(result.pca_coords[i, 1]),
            is_anomaly=bool(result.is_anomaly[i]),
            anomaly_reason=result.anomaly_reason[i],
        ))

    # Insights.
    assign_df = spend_sorted.copy()
    assign_df["cluster_index"] = result.labels
    assign_df["is_anomaly"] = result.is_anomaly
    label_map = {idx: labels[idx]["label"] for idx in range(result.k)}
    for ins in generate_insights(assign_df, label_map):
        cid = clusters_by_index[ins["cluster_index"]].id
        db.add(Insight(
            run_id=run.id,
            cluster_id=cid,
            period_month=ins["period_month"],
            kind=ins["kind"],
            severity=ins["severity"],
            body=ins["body"],
            impact_amount=ins["impact_amount"],
        ))

    db.commit()
    return {
        "run_id": run.id,
        "k": result.k,
        "silhouette": result.silhouette,
        "mean_ari": result.mean_ari,
        "n_transactions": len(spend_sorted),
        "n_anomalies": int(result.is_anomaly.sum()),
    }
