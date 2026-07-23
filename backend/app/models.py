"""SQLAlchemy ORM models.

Supabase-portability rules applied throughout:
- UUID primary keys stored as String(36) — SQLite has no native UUID type.
- DateTime(timezone=True), values always UTC.
- JSON via SQLAlchemy's portable JSON type, never SQLite-specific functions.
- No SQLite-only column types or defaults.

Every clustering execution creates one immutable `runs` row. Assignments,
clusters, and insights are keyed by run_id, so re-clustering never destroys
history — it just adds a new run that the API defaults to.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    algo: Mapped[str] = mapped_column(String(32), default="kmeans")
    k: Mapped[int] = mapped_column(Integer)
    silhouette: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean_ari: Mapped[float | None] = mapped_column(Float, nullable=True)
    n_transactions: Mapped[int] = mapped_column(Integer, default=0)
    # Full k-sweep, explained variance, feature names, etc. — renderable in UI.
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    # Pickled StandardScaler so future txns are scaled identically.
    scaler_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    clusters: Mapped[list[Cluster]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    txn_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    direction: Mapped[str] = mapped_column(String(8))  # debit | credit
    # spend | self_transfer | income | refund
    txn_kind: Mapped[str] = mapped_column(String(16), default="spend", index=True)
    counterparty_raw: Mapped[str] = mapped_column(Text)
    counterparty_normalized: Mapped[str] = mapped_column(Text, index=True)
    reference_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Deterministic key for idempotent ingest (see clean.dedup_key).
    dedup_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source_app: Mapped[str] = mapped_column(String(32), default="phonepe")
    parse_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    feature: Mapped[Feature | None] = relationship(
        back_populates="transaction", uselist=False, cascade="all, delete-orphan"
    )


class Feature(Base):
    __tablename__ = "features"

    transaction_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transactions.id"), primary_key=True
    )
    log_amount: Mapped[float] = mapped_column(Float)
    dow_sin: Mapped[float] = mapped_column(Float)
    dow_cos: Mapped[float] = mapped_column(Float)
    day_of_month_norm: Mapped[float] = mapped_column(Float)
    merchant_frequency: Mapped[float] = mapped_column(Float)
    recency_days: Mapped[float] = mapped_column(Float)
    is_recurring: Mapped[float] = mapped_column(Float)  # 0.0 / 1.0
    amount_stability: Mapped[float] = mapped_column(Float)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    transaction: Mapped[Transaction] = relationship(back_populates="feature")


# All engineered features — computed and stored for display/analysis.
FEATURE_COLUMNS = [
    "log_amount",
    "dow_sin",
    "dow_cos",
    "day_of_month_norm",
    "merchant_frequency",
    "recency_days",
    "is_recurring",
    "amount_stability",
]

# The subset actually fed to clustering. On a personal-scale dataset the
# cyclical day-of-week and recency features add dimensionality without signal
# and depress separation (silhouette 0.27 with all 8 vs 0.43 with these 4 on
# real data). Keep the vector small and every axis interpretable.
CLUSTERING_COLUMNS = [
    "log_amount",
    "merchant_frequency",
    "is_recurring",
    "amount_stability",
]


class Cluster(Base):
    __tablename__ = "clusters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id"), index=True
    )
    cluster_index: Mapped[int] = mapped_column(Integer)  # 0..k-1
    label: Mapped[str] = mapped_column(String(80))
    centroid_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    n_transactions: Mapped[int] = mapped_column(Integer, default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)

    run: Mapped[Run] = relationship(back_populates="clusters")


class ClusterAssignment(Base):
    __tablename__ = "cluster_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    transaction_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transactions.id"), index=True
    )
    cluster_id: Mapped[str] = mapped_column(String(36), ForeignKey("clusters.id"))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), index=True)
    distance_to_centroid: Mapped[float] = mapped_column(Float)
    pca_x: Mapped[float] = mapped_column(Float)
    pca_y: Mapped[float] = mapped_column(Float)
    is_anomaly: Mapped[bool] = mapped_column(Integer, default=0)
    anomaly_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)


class Insight(Base):
    __tablename__ = "insights"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), index=True)
    cluster_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    period_month: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    kind: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16), default="info")
    body: Mapped[str] = mapped_column(Text)
    impact_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)


class UnparsedRow(Base):
    __tablename__ = "unparsed_rows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_file: Mapped[str] = mapped_column(Text)
    raw_line: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
