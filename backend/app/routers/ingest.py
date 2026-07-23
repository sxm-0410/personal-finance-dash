"""Ingestion + reclustering endpoints."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Run, UnparsedRow
from app.schemas import RunOut, UnparsedOut
from app.services import ingest_file, recluster

router = APIRouter(tags=["ingest"])


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    password: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    suffix = Path(file.filename or "upload").suffix or ".dat"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        stats = ingest_file(db, tmp_path, password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)  # never keep the raw statement
    return stats


@router.post("/recluster")
def trigger_recluster(db: Session = Depends(get_db)):
    try:
        return recluster(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs", response_model=list[RunOut])
def list_runs(latest: bool = False, db: Session = Depends(get_db)):
    stmt = select(Run).order_by(Run.created_at.desc())
    if latest:
        stmt = stmt.limit(1)
    return db.execute(stmt).scalars().all()


@router.get("/unparsed", response_model=list[UnparsedOut])
def list_unparsed(limit: int = 200, db: Session = Depends(get_db)):
    return db.execute(
        select(UnparsedRow).order_by(UnparsedRow.created_at.desc()).limit(limit)
    ).scalars().all()
