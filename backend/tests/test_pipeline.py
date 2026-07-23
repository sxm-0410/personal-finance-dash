"""End-to-end pipeline smoke tests against synthetic data.

Runs entirely on generated data — no real statements, no network, no DB
migration needed (uses an in-memory SQLite).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401 - registers tables on Base.metadata
from app.db import Base
from app.pipeline.adapters.phonepe_csv import PhonePeCSVAdapter
from app.pipeline.clean import clean
from app.pipeline.features import build_features
from scripts.gen_synthetic import _rows

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_phonepe.csv"


@pytest.fixture(scope="module")
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # one shared in-memory DB across sessions
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    yield Session
    Base.metadata.drop_all(engine)


def test_csv_adapter_parses_all():
    res = PhonePeCSVAdapter().parse(FIXTURE)
    assert res.parse_rate == 1.0
    assert len(res.rows) > 100


def test_clean_classifies_kinds():
    res = PhonePeCSVAdapter().parse(FIXTURE)
    df = clean(res.rows, owner_terms=["self"])
    kinds = set(df["txn_kind"])
    assert "spend" in kinds
    assert "self_transfer" in kinds  # generator emits paired transfers
    assert "income" in kinds         # salary credits


def test_features_shape():
    res = PhonePeCSVAdapter().parse(FIXTURE)
    df = clean(res.rows, owner_terms=["self"])
    df["id"] = [f"t{i}" for i in range(len(df))]
    feats = build_features(df)
    assert not feats.empty
    assert set(feats["is_recurring"].unique()) <= {0.0, 1.0}
    # Subscriptions should trip the recurring flag somewhere.
    assert feats["is_recurring"].sum() > 0


def test_full_ingest_and_recluster(db):
    from app.services import ingest_file, recluster

    session = db()
    stats = ingest_file(session, FIXTURE)
    assert stats["inserted"] > 100

    # Idempotent re-ingest inserts nothing new.
    again = ingest_file(session, FIXTURE)
    assert again["inserted"] == 0

    result = recluster(session)
    assert 2 <= result["k"] <= 8
    assert result["silhouette"] is not None
    session.close()
