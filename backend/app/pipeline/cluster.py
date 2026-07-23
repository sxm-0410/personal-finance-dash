"""Clustering engine (Layer 4).

Pipeline: scale -> k-sweep (pick best silhouette, capped) -> fit KMeans ->
bootstrap stability (ARI) -> DBSCAN + robust-z anomaly union -> PCA to 2D.

Returns a ClusterResult carrying everything the persistence layer needs to
write one immutable run.
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN, KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

from app.config import settings
from app.models import FEATURE_COLUMNS


@dataclass
class ClusterResult:
    k: int
    labels: np.ndarray            # cluster index per row
    distances: np.ndarray         # distance to assigned centroid
    pca_coords: np.ndarray        # (n, 2)
    is_anomaly: np.ndarray        # bool per row
    anomaly_reason: list[str | None]
    silhouette: float | None
    mean_ari: float | None
    centroids_original: np.ndarray  # centroids inverse-transformed to raw units
    scaler_blob: bytes
    metrics: dict = field(default_factory=dict)


def _select_k(X: np.ndarray) -> tuple[int, list[dict]]:
    sweep: list[dict] = []
    n = X.shape[0]
    kmax = min(settings.k_max, max(2, n - 1))
    best_k, best_score = 2, -1.0
    for k in range(settings.k_min, kmax + 1):
        km = KMeans(n_clusters=k, n_init=settings.kmeans_n_init,
                    random_state=settings.random_seed)
        labels = km.fit_predict(X)
        sil = silhouette_score(X, labels) if len(set(labels)) > 1 else -1.0
        sweep.append({"k": k, "inertia": float(km.inertia_), "silhouette": float(sil)})
        if sil > best_score:
            best_score, best_k = sil, k
    return best_k, sweep


def _stability(X: np.ndarray, k: int, base_labels: np.ndarray) -> float | None:
    n = X.shape[0]
    if n < 20:
        return None
    rng = np.random.default_rng(settings.random_seed)
    aris: list[float] = []
    sample_n = max(k + 1, int(settings.stability_sample_frac * n))
    for _ in range(settings.stability_seeds):
        idx = rng.choice(n, size=sample_n, replace=False)
        km = KMeans(n_clusters=k, n_init=10, random_state=int(rng.integers(1e6)))
        sub_labels = km.fit_predict(X[idx])
        aris.append(adjusted_rand_score(base_labels[idx], sub_labels))
    return float(np.mean(aris))


def _anomalies(
    X: np.ndarray, df: pd.DataFrame
) -> tuple[np.ndarray, list[str | None]]:
    n = X.shape[0]
    flags = np.zeros(n, dtype=bool)
    reasons: list[str | None] = [None] * n

    # DBSCAN density outliers.
    if n >= settings.dbscan_min_samples + 1:
        # eps from median pairwise-ish scale; simple robust default.
        dist = np.linalg.norm(X - X.mean(axis=0), axis=1)
        eps = np.percentile(dist, 90) or 1.0
        db = DBSCAN(eps=float(eps), min_samples=settings.dbscan_min_samples)
        db_labels = db.fit_predict(X)
        for i in np.where(db_labels == -1)[0]:
            flags[i] = True
            reasons[i] = "density outlier (DBSCAN)"

    # Per-merchant robust z-score on amount (median / MAD).
    amounts = df["amount"].to_numpy()
    for merchant, idx in df.groupby("counterparty_normalized").groups.items():
        pos = [df.index.get_loc(i) for i in idx]
        vals = amounts[pos]
        if len(vals) < 3:
            continue
        med = np.median(vals)
        mad = np.median(np.abs(vals - med)) or 1e-9
        z = 0.6745 * (vals - med) / mad
        for j, p in enumerate(pos):
            if abs(z[j]) > settings.robust_z_threshold:
                flags[p] = True
                reasons[p] = f"unusual amount for {merchant} (z={z[j]:.1f})"
    return flags, reasons


def run_clustering(features_df: pd.DataFrame, spend_df: pd.DataFrame) -> ClusterResult:
    """features_df: rows aligned to spend_df (same order). spend_df has 'amount'."""
    X_raw = features_df[FEATURE_COLUMNS].to_numpy(dtype=float)
    scaler = StandardScaler()
    X = scaler.fit_transform(X_raw)

    k, sweep = _select_k(X)
    km = KMeans(n_clusters=k, n_init=settings.kmeans_n_init,
                random_state=settings.random_seed)
    labels = km.fit_predict(X)
    sil = silhouette_score(X, labels) if len(set(labels)) > 1 else None
    mean_ari = _stability(X, k, labels)

    # Distance to assigned centroid.
    dists = np.linalg.norm(X - km.cluster_centers_[labels], axis=1)

    # Centroids back in original feature units for labeling.
    centroids_original = scaler.inverse_transform(km.cluster_centers_)

    flags, reasons = _anomalies(X, spend_df.reset_index(drop=True))

    # PCA to 2D for the scatter plot.
    n_comp = min(2, X.shape[1], X.shape[0])
    pca = PCA(n_components=n_comp, random_state=settings.random_seed)
    coords = pca.fit_transform(X)
    if coords.shape[1] == 1:
        coords = np.column_stack([coords, np.zeros(len(coords))])
    explained = [float(v) for v in pca.explained_variance_ratio_]

    metrics = {
        "k_sweep": sweep,
        "chosen_k": k,
        "pca_explained_variance": explained,
        "feature_columns": FEATURE_COLUMNS,
        "n_anomalies": int(flags.sum()),
    }

    return ClusterResult(
        k=k,
        labels=labels,
        distances=dists,
        pca_coords=coords,
        is_anomaly=flags,
        anomaly_reason=reasons,
        silhouette=float(sil) if sil is not None else None,
        mean_ari=mean_ari,
        centroids_original=centroids_original,
        scaler_blob=pickle.dumps(scaler),
        metrics=metrics,
    )
