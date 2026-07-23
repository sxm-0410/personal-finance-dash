"""Transaction listing with filters."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ClusterAssignment, Transaction
from app.schemas import TransactionOut
from app.services import latest_run_id

router = APIRouter(tags=["transactions"])


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    start: datetime | None = None,
    end: datetime | None = None,
    txn_kind: str | None = None,
    merchant: str | None = None,
    cluster_index: int | None = None,
    is_anomaly: bool | None = None,
    limit: int = Query(500, le=5000),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    stmt = select(Transaction)
    if start:
        stmt = stmt.where(Transaction.txn_date >= start)
    if end:
        stmt = stmt.where(Transaction.txn_date <= end)
    if txn_kind:
        stmt = stmt.where(Transaction.txn_kind == txn_kind)
    if merchant:
        stmt = stmt.where(
            Transaction.counterparty_normalized.ilike(f"%{merchant}%")
        )

    if cluster_index is not None or is_anomaly is not None:
        run_id = latest_run_id(db)
        if run_id is None:
            return []
        sub = select(ClusterAssignment.transaction_id).where(
            ClusterAssignment.run_id == run_id
        )
        if is_anomaly is not None:
            sub = sub.where(ClusterAssignment.is_anomaly == is_anomaly)
        if cluster_index is not None:
            from app.models import Cluster
            cluster_ids = select(Cluster.id).where(
                Cluster.run_id == run_id,
                Cluster.cluster_index == cluster_index,
            )
            sub = sub.where(ClusterAssignment.cluster_id.in_(cluster_ids))
        stmt = stmt.where(Transaction.id.in_(sub))

    stmt = stmt.order_by(Transaction.txn_date.desc()).limit(limit).offset(offset)
    return db.execute(stmt).scalars().all()
