"""FastAPI application entrypoint."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import clusters, ingest, insights, transactions

app = FastAPI(title="Personal Finance Dashboard API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_prefix = "/api"
app.include_router(ingest.router, prefix=api_prefix)
app.include_router(transactions.router, prefix=api_prefix)
app.include_router(clusters.router, prefix=api_prefix)
app.include_router(insights.router, prefix=api_prefix)


@app.get("/api/health")
def health():
    return {"status": "ok"}
