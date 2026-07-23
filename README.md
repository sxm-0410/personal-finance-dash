# Personal Finance Dashboard — Spending Clusters

Ingests UPI transaction history (PhonePe CSV/PDF) and uses **unsupervised ML** to
group transactions into natural *spending clusters* — patterns discovered from the
data itself, not from manually assigned categories. The dashboard visualizes those
clusters and surfaces plain-language insights about how spending shifts over time.

> Personal analytics tool and applied-ML portfolio piece: clustering + feature
> engineering behind a FastAPI + React delivery.

## What it does

- **Ingests** PhonePe statements (CSV and PDF) through pluggable source adapters.
  Nothing is silently dropped — unparseable rows go to a review queue.
- **Cleans** the data: idempotent dedup, self-transfer / income / refund
  classification, three-tier merchant normalization, and a privacy pass that hashes
  reference IDs and masks UPI handles before anything is stored.
- **Engineers 7 features** including cyclical day-of-week, per-merchant amount
  stability, and an explicit recurring-payment detector.
- **Clusters** with K-means (silhouette-driven `k`, capped at 8), measures cluster
  **stability** via bootstrap Adjusted Rand Index, flags **anomalies** with a
  DBSCAN + robust-z union, and projects to 2D with PCA for the scatter plot.
- **Labels** each cluster with a human-readable name from a rule table over the
  centroids, and generates **ranked, plain-language insights** ("your recurring-
  subscription cluster grew 18% this month").
- **Serves** it all via FastAPI and renders an interactive React dashboard.

## Results on the bundled synthetic dataset

Run against `backend/tests/fixtures/synthetic_phonepe.csv` (263 transactions,
8 months):

| Metric | Value | Target (PRD) |
|---|---|---|
| Parse rate | 100% | > 90% |
| Silhouette score | 0.34 | > 0.3 |
| Cluster stability (mean ARI) | 0.97 | — (higher = more stable) |
| Clusters discovered | 3 | interpretable |

Discovered clusters: *Recurring bills & subscriptions* (100% recurring),
*Small frequent purchases* (~₹68 avg), *Large one-off purchases*.

## Architecture

```
PhonePe export ─▶ adapter ─▶ clean ─▶ features ─▶ clustering ─▶ SQLite/Postgres
  (CSV | PDF)      (sniff)   (dedup,   (7 feats,   (KMeans +        │
                             privacy)  recurring)   DBSCAN, PCA)    ▼
                                                              FastAPI  ─▶  React
                                                              (JSON API)   dashboard
```

- **ML/data:** Python 3.12, pandas, scikit-learn (StandardScaler, KMeans, DBSCAN,
  PCA), rapidfuzz for merchant matching.
- **Backend:** FastAPI, SQLAlchemy, Alembic.
- **Database:** SQLite locally; **Supabase/Postgres-portable** — `DATABASE_URL` is
  the only thing that changes (UUID string keys, tz-aware UTC, JSON columns, all
  migrations through Alembic).
- **Frontend:** React + TypeScript + Tailwind v4 + Recharts. Theme-aware (light/dark),
  colorblind-safe categorical palette, anomalies encoded by shape *and* color.

Every clustering execution writes one **immutable `runs` row**; clusters,
assignments, and insights are keyed by `run_id`, so re-clustering never destroys
history — the API just defaults to the latest run.

## Quick start

Prereqs: [uv](https://docs.astral.sh/uv/) and Node 20+.

```bash
./dev.sh          # starts backend :8000 and frontend :5173
```

Then open http://localhost:5173 and click **Upload statement** (a synthetic CSV
lives at `backend/tests/fixtures/`, regenerate with the command below). Or drive it
from the API:

```bash
cd backend
uv run python -m scripts.gen_synthetic          # writes the synthetic fixture
uv run uvicorn app.main:app --reload            # API + docs at /docs
curl -F "file=@tests/fixtures/synthetic_phonepe.csv" localhost:8000/api/upload
curl -X POST localhost:8000/api/recluster
```

### Scoring the PDF parser against the CSV oracle

If you have both a PDF and a CSV export of the same period, measure the PDF parse
rate against the reliable CSV:

```bash
uv run python -m scripts.reconcile statement.pdf statement.csv --password <pw>
```

### Tests & lint

```bash
cd backend  && uv run pytest && uv run ruff check app scripts
cd frontend && npx tsc --noEmit && npm run lint && npm run build
```

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/upload` | Parse + persist a statement (multipart, optional `password`) |
| `POST /api/recluster` | Re-run features → clustering → labels → insights (new run) |
| `GET /api/runs?latest=true` | Run metadata + metrics |
| `GET /api/clusters` | Latest run's clusters with labels + centroid evidence |
| `GET /api/clusters/points` | Scatter payload (PCA coords, anomaly flags) |
| `GET /api/spend-over-time` | Month × cluster totals for the trend chart |
| `GET /api/insights` | Ranked plain-language insights |
| `GET /api/transactions` | Filterable transaction list |
| `GET /api/unparsed` | Manual-review queue for rows that failed to parse |

## Privacy

Real financial data never enters the repo — `.gitignore` blocks PDFs, CSVs, DB
files, and `.env`. Reference IDs are hashed and UPI handles masked at ingest; raw
uploads are parsed to a temp file and deleted immediately, never persisted.

## Roadmap / non-goals (v1)

Single-user only. No live bank linking, net-worth tracking, or budgeting. Scheduled
re-clustering and additional source adapters (GPay, Paytm) are natural next steps —
the adapter interface already supports them.
