"""Cluster read endpoints: clusters, scatter points, spend-over-time."""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Cluster, ClusterAssignment, Transaction
from app.schemas import ClusterOut, ScatterPoint, SpendOverTime
from app.services import latest_run_id

router = APIRouter(tags=["clusters"])


def _resolve_run(db: Session, run_id: str | None) -> str:
    rid = run_id or latest_run_id(db)
    if rid is None:
        raise HTTPException(status_code=404, detail="No clustering run yet")
    return rid


@router.get("/clusters", response_model=list[ClusterOut])
def list_clusters(run_id: str | None = None, db: Session = Depends(get_db)):
    rid = _resolve_run(db, run_id)
    return db.execute(
        select(Cluster).where(Cluster.run_id == rid).order_by(Cluster.cluster_index)
    ).scalars().all()


@router.get("/clusters/points", response_model=list[ScatterPoint])
def scatter_points(run_id: str | None = None, db: Session = Depends(get_db)):
    rid = _resolve_run(db, run_id)
    rows = db.execute(
        select(ClusterAssignment, Transaction, Cluster)
        .join(Transaction, Transaction.id == ClusterAssignment.transaction_id)
        .join(Cluster, Cluster.id == ClusterAssignment.cluster_id)
        .where(ClusterAssignment.run_id == rid)
    ).all()
    return [
        ScatterPoint(
            transaction_id=a.transaction_id,
            pca_x=a.pca_x,
            pca_y=a.pca_y,
            amount=float(t.amount),
            counterparty=t.counterparty_normalized,
            txn_date=t.txn_date,
            cluster_index=c.cluster_index,
            is_anomaly=bool(a.is_anomaly),
            anomaly_reason=a.anomaly_reason,
        )
        for a, t, c in rows
    ]


@router.get("/spend-over-time", response_model=SpendOverTime)
def spend_over_time(run_id: str | None = None, db: Session = Depends(get_db)):
    rid = _resolve_run(db, run_id)
    rows = db.execute(
        select(Transaction.txn_date, Transaction.amount, Cluster.cluster_index,
               Cluster.label)
        .join(ClusterAssignment, ClusterAssignment.transaction_id == Transaction.id)
        .join(Cluster, Cluster.id == ClusterAssignment.cluster_id)
        .where(ClusterAssignment.run_id == rid)
    ).all()

    months: set[str] = set()
    by_cluster: dict[int, dict] = {}
    totals: dict[tuple[int, str], float] = defaultdict(float)
    for txn_date, amount, cluster_index, label in rows:
        m = txn_date.strftime("%Y-%m")
        months.add(m)
        by_cluster.setdefault(cluster_index, {"label": label})
        totals[(cluster_index, m)] += float(amount)

    ordered_months = sorted(months)
    series = []
    for cidx in sorted(by_cluster):
        series.append({
            "cluster_index": cidx,
            "label": by_cluster[cidx]["label"],
            "values": [round(totals[(cidx, m)], 2) for m in ordered_months],
        })
    return SpendOverTime(months=ordered_months, series=series)
