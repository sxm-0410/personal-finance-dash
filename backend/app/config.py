"""Application configuration.

Uses pydantic-settings so every value can be overridden by an env var or a
`.env` file. The only setting that changes between local dev and Supabase is
DATABASE_URL — swap the SQLite URL for a Postgres one and nothing else moves.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR.parent / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLite locally; set DATABASE_URL to a Supabase Postgres URL to switch.
    database_url: str = f"sqlite:///{BACKEND_DIR / 'finance.db'}"

    # CORS origin for the Vite dev server.
    frontend_origin: str = "http://localhost:5173"

    # Clustering knobs (see PRD non-functional requirements).
    k_min: int = 2
    k_max: int = 8
    kmeans_n_init: int = 25
    stability_seeds: int = 20
    stability_sample_frac: float = 0.8
    random_seed: int = 42

    # Anomaly detection.
    robust_z_threshold: float = 3.5
    dbscan_min_samples: int = 4

    # Merchant fuzzy-match threshold (rapidfuzz token_set_ratio).
    fuzzy_threshold: int = 88


settings = Settings()
