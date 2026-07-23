"""Pydantic response models."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    txn_date: datetime
    amount: float
    direction: str
    txn_kind: str
    counterparty_normalized: str
    counterparty_raw: str
    parse_confidence: float


class ClusterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    cluster_index: int
    label: str
    centroid_summary: dict
    n_transactions: int
    total_amount: float


class ScatterPoint(BaseModel):
    transaction_id: str
    pca_x: float
    pca_y: float
    amount: float
    counterparty: str
    txn_date: datetime
    cluster_index: int
    is_anomaly: bool
    anomaly_reason: str | None


class InsightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    period_month: str
    kind: str
    severity: str
    body: str
    impact_amount: float


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    algo: str
    k: int
    silhouette: float | None
    mean_ari: float | None
    n_transactions: int
    metrics_json: dict


class UnparsedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source_file: str
    raw_line: str
    reason: str
    created_at: datetime


class SpendOverTime(BaseModel):
    months: list[str]
    series: list[dict]  # [{cluster_index, label, values: [..]}]
