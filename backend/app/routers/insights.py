"""Insights endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Insight
from app.schemas import InsightOut
from app.services import latest_run_id

router = APIRouter(tags=["insights"])


@router.get("/insights", response_model=list[InsightOut])
def list_insights(
    run_id: str | None = None,
    month: str | None = None,
    db: Session = Depends(get_db),
):
    rid = run_id or latest_run_id(db)
    if rid is None:
        return []
    stmt = select(Insight).where(Insight.run_id == rid)
    if month:
        stmt = stmt.where(Insight.period_month == month)
    stmt = stmt.order_by(Insight.impact_amount.desc())
    return db.execute(stmt).scalars().all()
