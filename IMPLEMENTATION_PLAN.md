# Implementation Plan — Personal Finance Dashboard with Spending Clusters

**Target:** one overnight session (~8.5 working hours), full vertical slice through Phase 6 (insights).
**Decisions locked:** SQLite local with Supabase-shaped schema · both PDF and CSV exports available · scope includes auto-generated insights and manual re-clustering.

---

## 0. Guiding principles for tonight

1. **The spine ships first.** Every layer must leave the system runnable end-to-end. If you stop at 3am, you stop with a working (dumber) product, not a half-wired one.
2. **CSV is the oracle, PDF is the deliverable.** You have both exports of the same period. Parse the CSV (easy, reliable) to get ground truth, then score the PDF parser against it. This makes the PRD's ">90% parsed" metric a number you can print, not a claim.
3. **Deterministic over clever.** Rule-based cluster labeling and template-rendered insights. No LLM in the pipeline — keeps it offline, private, reproducible, and explainable in an interview.
4. **Small feature set.** The PRD flags curse-of-dimensionality on a few-thousand-row personal dataset. Cap at 7 features. Resist adding more.
5. **Runs are immutable.** Every clustering execution writes a new `runs` row; assignments are keyed by `run_id`. Re-clustering never destroys history, and you can diff runs later.

**Cut lines** (drop in this order if behind schedule): stability analysis → UMAP → merchant fuzzy-matching → insights → DBSCAN. Never cut: the vertical slice.

---

## Repo layout

```
personal-finance-dash/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app + routers
│   │   ├── config.py               # pydantic-settings, DATABASE_URL
│   │   ├── db.py                   # engine, session, Base
│   │   ├── models.py               # SQLAlchemy ORM
│   │   ├── schemas.py              # pydantic response models
│   │   ├── routers/
│   │   │   ├── transactions.py
│   │   │   ├── clusters.py
│   │   │   ├── insights.py
│   │   │   └── ingest.py           # /upload, /recluster
│   │   └── pipeline/
│   │       ├── adapters/
│   │       │   ├── base.py         # SourceAdapter protocol
│   │       │   ├── phonepe_csv.py
│   │       │   └── phonepe_pdf.py
│   │       ├── clean.py
│   │       ├── features.py
│   │       ├── cluster.py
│   │       ├── label.py
│   │       └── insights.py
│   ├── alembic/                    # migrations (Supabase portability)
│   ├── tests/
│   │   └── fixtures/               # SYNTHETIC only — never real data
│   └── pyproject.toml
├── frontend/                       # Vite + React + TS + Tailwind + shadcn
├── notebooks/                      # 01_explore.ipynb, 02_k_selection.ipynb
├── data/                           # gitignored. Real statements live here.
└── .gitignore
```

---

## Layer 0 — Foundation (~30 min, 0:00–0:30)

**Why first:** Python 3.9.6 is your system interpreter. It's past end-of-life and numpy 2.x / modern scikit-learn wheels won't install cleanly. Fix this before writing a line of pipeline code — discovering it at 2am mid-`pip install` is the classic overnight-project killer.

- [ ] Install Python 3.12 (`brew install python@3.12`) and `uv` (`curl -LsSf https://astral.sh/uv/install.sh | sh`) — uv makes the dependency loop seconds instead of minutes, which matters tonight.
- [ ] `git init`. Write `.gitignore` **before the first commit**: `data/`, `*.pdf`, `*.csv`, `*.db`, `.env`, `__pycache__/`, `node_modules/`.
- [ ] `uv init backend && uv add fastapi uvicorn[standard] sqlalchemy alembic pydantic-settings pandas scikit-learn pdfplumber pypdf rapidfuzz python-multipart` + dev: `pytest ruff`.
- [ ] `npm create vite@latest frontend -- --template react-ts`, then Tailwind + `shadcn init` + `recharts`.
- [ ] Hello-world FastAPI on :8000, Vite on :5173 with proxy to /api. Confirm both respond.

**Checkpoint:** two servers running, clean git tree, no real data tracked.

---

## Layer 1 — Ingestion & adapters (~75 min, 0:30–1:45)

The PRD demands portability across PhonePe/GPay/Paytm. Solve it with one narrow interface and two implementations.

**Interface** (`adapters/base.py`):
```python
class RawTransaction(TypedDict):
    txn_date: datetime; amount: Decimal; direction: Literal["debit","credit"]
    counterparty_raw: str; reference_id: str | None; source_app: str
    parse_confidence: float; raw_line: str      # for the manual-review queue

class SourceAdapter(Protocol):
    name: str
    def sniff(self, path: Path) -> bool: ...
    def parse(self, path: Path, password: str | None) -> ParseResult: ...
```
`ParseResult` carries `rows`, `unparsed` (lines that failed, with reason), and `stats`. **Never silently drop a row** — the PRD calls this out, and the unparsed list becomes a UI review queue later.

**1a. CSV adapter first (~20 min).** Trivial, gives you a real dataset within the first two hours. Everything downstream can be built and tested while the PDF parser is still rough.

**1b. PDF adapter (~40 min).**
- Decrypt with `pypdf` if encrypted (PhonePe locks statements with mobile/DOB; take password as an argument, never persist it).
- Extract with `pdfplumber` — try `extract_table()` per page, fall back to `extract_text()` + line regex. PhonePe rows are typically `DATE / TIME / TRANSACTION DETAILS / TYPE / AMOUNT` with the counterparty on a continuation line, so buffer lines until a date anchor starts the next record.
- Tag every row with `parse_confidence` (1.0 from a clean table cell, lower from regex fallback).

**1c. The reconciliation harness (~15 min) — do not skip.**
`scripts/reconcile.py` loads both exports of the same period and matches on `(date, amount, direction)` as a multiset. Prints: matched %, PDF-only rows (false positives), CSV-only rows (misses). This is your Success Metric #3, measured, and it turns PDF debugging from squinting at text into a shrinking error list.

**Checkpoint:** `python -m scripts.reconcile` prints a parse rate. Push it past 90%.

---

## Layer 2 — Cleaning & normalization (~60 min, 1:45–2:45)

- **Dedupe** on `reference_id` (UTR) when present, else `(date, amount, counterparty_raw)`. PDF and CSV of overlapping periods *will* collide; make ingest idempotent so re-uploads are safe.
- **Self-transfer classification.** The PRD flags this as a totals-distorting risk. Detect via: counterparty matching your own name/UPI handles, plus a `self_transfer` heuristic for debit/credit pairs of equal amount within a short window. Store as a `txn_kind` enum (`spend` / `self_transfer` / `income` / `refund`) rather than deleting — you want it excluded from spend analysis but visible in the table.
- **Merchant normalization**, in three escalating tiers:
  1. Deterministic scrub: uppercase, strip UPI suffixes (`@ybl`, `@paytm`), strip trailing digits/store codes, collapse whitespace.
  2. `rapidfuzz` clustering of the remaining distinct names at ~88 token_set_ratio → canonical form = most frequent variant in each group.
  3. `merchant_overrides.yaml`, hand-edited, applied last and always wins. Ten minutes of manual mapping beats an hour of fuzzy-matching tuning.
- **Amount hygiene:** strip `₹`/commas, coerce to `Decimal`, assert positive with direction carried separately.

**Privacy pass, applied here at ingest** (Non-Functional Req #1): hash `reference_id` (SHA-256, truncated), mask UPI IDs to `abc***@ybl` before persistence, and keep the raw PDF in gitignored `data/` — never in the DB.

**Checkpoint:** a clean DataFrame with `txn_kind` and `counterparty_normalized`; distinct-merchant count dropped meaningfully vs. raw.

---

## Layer 3 — Feature engineering (~60 min, 2:45–3:45)

Seven features, chosen to be individually defensible:

| Feature | Definition | Why |
|---|---|---|
| `log_amount` | `log1p(amount)` | PRD's #1 ML risk — rent would otherwise dominate every distance |
| `dow_sin`, `dow_cos` | cyclical day-of-week | Sunday and Monday must be adjacent; raw 0–6 makes them maximally far apart |
| `day_of_month_norm` | day / days_in_month | separates start-of-month bills from mid-month drift |
| `merchant_frequency` | log of txn count for that merchant | separates one-off merchants from habitual ones |
| `recency_days` | days since previous txn at same merchant | captures cadence |
| `is_recurring` | see below | the single most interpretable feature you'll have |
| `amount_stability` | 1 − (per-merchant amount CV) | subscriptions are amount-stable; groceries are not |

**Recurring detection** (compute *before* clustering — it's an input, not an output): for each merchant with ≥3 transactions, take inter-arrival days; flag recurring if the coefficient of variation of intervals < 0.25 *and* mean interval falls near 7/30/365 within tolerance. This is a real algorithm you can explain in one sentence.

Then `StandardScaler` on the full matrix. **Persist the fitted scaler** with the run — you need identical scaling to place future transactions into existing clusters.

**Checkpoint:** feature matrix persisted; sanity-check that `log_amount` is roughly symmetric now.

---

## Layer 4 — Clustering engine (~75 min, 3:45–5:00)

**4a. K selection.** Sweep k = 2..10, `n_init=25` (small dataset, cheap, buys stability). Record inertia + silhouette for every k. Auto-pick the best silhouette, but **hard-cap at k ≤ 8** — a personal dashboard with 9 clusters is unreadable regardless of what the score says. Persist the whole sweep in `runs.metrics_json` so the elbow curve is renderable in the UI.

**4b. Stability analysis** (this is the detail that makes it a portfolio piece). Bootstrap-resample 80% of rows, refit, compute Adjusted Rand Index against the full-data labels across ~20 seeds. Report mean ARI. It directly answers the PRD's "K-means can be unstable on small data" concern with evidence instead of a caveat. *First cut line if you're behind.*

**4c. DBSCAN anomaly pass.** Same scaled matrix, `eps` chosen from the k-distance elbow, `min_samples ≈ 4`. Label `-1` points are anomalies. Union this with a simpler, more explainable signal: per-merchant robust z-score (median/MAD) > 3.5. Store `is_anomaly` + `anomaly_reason` so the UI can say *why*, not just flag it.

**4d. PCA to 2D** for the scatter plot; persist `pca_x`, `pca_y` per transaction and the explained-variance ratio (label the axes honestly in the UI). UMAP is a nice-to-have, not tonight.

**Checkpoint:** a `run` row with silhouette ≥ 0.3 (Success Metric #2) and per-transaction assignments.

---

## Layer 5 — Labeling & insights (~60 min, 5:00–6:00)

**5a. Cluster labeling.** Invert the scaler to get centroids in *original* units, then rank each centroid's features into percentile buckets (low/mid/high) and match against an ordered rule table:

| Condition | Label |
|---|---|
| `is_recurring` high + `amount_stability` high | "Recurring bills & subscriptions" |
| `log_amount` low + `merchant_frequency` high | "Small frequent purchases" |
| `log_amount` high + `merchant_frequency` low | "Large one-off purchases" |
| `dow` weekend-weighted + mid amount | "Weekend discretionary spend" |
| *(fallback)* | "Mid-size regular spend" — templated from top 2 distinguishing features |

Always store the numeric `centroid_summary` alongside the label, so the UI can show the evidence ("avg ₹340 · 12×/month · 78% recurring") next to the name. That's the PRD's interpretability requirement handled.

**5b. Insights generation.** Per (cluster × month), compute vs. prior month: total spend Δ%, txn count Δ, new merchants appearing, largest single txn, anomaly count. Render through sentence templates, then **rank by absolute impact in ₹ and keep the top 5** — an insights feed that lists everything is noise. Store in an `insights` table with a `severity` field so the UI can style them.

**Checkpoint:** `GET /insights` would return sentences a non-technical person understands.

---

## Layer 6 — Persistence (~40 min, 6:00–6:40)

Schema (extends the PRD draft with an explicit `runs` table, which its `run_id` columns already imply):

```
runs                 id, created_at, algo, k, silhouette, mean_ari,
                     n_transactions, metrics_json, scaler_blob
transactions         id, txn_date, amount, direction, txn_kind,
                     counterparty_raw, counterparty_normalized,
                     reference_hash, source_app, parse_confidence, created_at
features             transaction_id → 7 feature cols, computed_at
clusters             id, run_id, cluster_index, label, centroid_summary(JSON),
                     n_transactions, total_amount
cluster_assignments  transaction_id, cluster_id, run_id,
                     distance_to_centroid, pca_x, pca_y,
                     is_anomaly, anomaly_reason
insights             id, run_id, cluster_id, period_month, kind,
                     severity, body, impact_amount
unparsed_rows        id, source_file, raw_line, reason, created_at
```

**Supabase-portability rules** (so the later swap is a one-line `DATABASE_URL` change):
- UUID primary keys stored as `String(36)` — SQLite has no native UUID.
- `DateTime(timezone=True)`, always UTC.
- JSON via SQLAlchemy's `JSON` type, never SQLite-specific functions.
- All schema changes through Alembic from the start. No `create_all` shortcuts.
- No raw SQL with SQLite-only syntax.

Index `transactions.txn_date`, `cluster_assignments.run_id`, `insights.run_id`.

---

## Layer 7 — FastAPI (~40 min, 6:40–7:20)

| Endpoint | Notes |
|---|---|
| `POST /api/upload` | multipart + optional `password`; runs adapter → clean → persist; returns parse stats & unparsed count |
| `POST /api/recluster` | triggers features → cluster → label → insights; returns new `run_id`. BackgroundTask; it's seconds, don't over-engineer |
| `GET /api/runs` | run history with metrics; `?latest=true` |
| `GET /api/transactions` | filters: date range, cluster, `txn_kind`, merchant, `is_anomaly`; paginated |
| `GET /api/clusters` | latest run's clusters + label + centroid_summary + totals |
| `GET /api/clusters/{id}/points` | scatter payload (pca_x/y, amount, merchant, anomaly flag) |
| `GET /api/spend-over-time` | month × cluster matrix for the stacked chart |
| `GET /api/insights` | ranked, filterable by month |
| `GET /api/unparsed` | the manual-review queue |

Every cluster-reading endpoint defaults to the latest `run_id` but accepts an override — that's what makes re-clustering non-destructive in practice. Enable CORS for :5173.

**Checkpoint:** `/docs` exercises the whole pipeline. **The backend is now independently demoable — this is your real safety line.**

---

## Layer 8 — React dashboard (~90 min, 7:20–8:50)

Before writing any chart code, load the `dataviz` skill — one consistent palette and axis treatment across three charts is what separates "portfolio piece" from "student project," and retrofitting it later costs more than doing it now.

Build in this order, committing after each:

1. **Shell + data layer** (15 min) — layout, `fetch` hooks, loading/error states.
2. **Cluster scatter** (25 min) — recharts `ScatterChart` on PCA coords, colored by cluster, anomalies as a distinct mark (ring/triangle, not just a color — must survive colorblind viewing). Tooltip shows merchant/amount/date. Click → filters the table.
3. **Spend-over-time** (20 min) — stacked area, month × cluster, using the same cluster colors as the scatter. Shared color identity across charts is what makes it read as one system.
4. **Transaction table** (20 min) — shadcn table, filters for date/cluster/kind/anomaly, sortable amount, anomaly badge with `anomaly_reason` on hover.
5. **Insight cards + run header** (10 min) — top-5 insight feed; header strip showing k, silhouette, mean ARI, txn count, and a "Re-cluster" button.

**Checkpoint:** click a cluster in the scatter → table filters to it. That single interaction is the demo.

---

## Layer 9 — Close-out (~30 min)

- [ ] `README.md`: architecture diagram, setup, the reconciliation parse-rate number, silhouette and ARI, one screenshot. Write it tonight while the details are fresh — this is the artifact a recruiter actually reads.
- [ ] `make dev` / single script that starts both servers.
- [ ] Verify `git status` shows no `data/`, `.db`, or PDF. Then first push.
- [ ] Log open questions with your answers now that you've seen real data (esp. PRD §13: transactions vs. time-periods as the clustering unit).

---

## Risk register — where this actually goes wrong tonight

| Risk | Mitigation |
|---|---|
| **PDF layout resists parsing** (highest probability) | CSV adapter already carries the pipeline. Time-box PDF to 45 min; if the reconciliation rate is under 70%, commit what you have, move on, return with fresh eyes. Do not let Layer 1 eat Layer 4. |
| Silhouette stuck below 0.3 | Usually too many features or self-transfers left in. Drop to 4 features (log_amount, frequency, is_recurring, day_of_month) before touching k. |
| Clusters are technically valid but boring | Symptom of `log_amount` dominating. Check per-feature centroid spread; consider excluding the top 1% of amounts from *fitting* and assigning them after. |
| Python 3.9 wheel failures | Layer 0, task 1. Non-negotiable. |
| Scope creep at 4am | The cut-line list at the top. UMAP, auth, multi-user, and live re-clustering schedules are all explicitly *not tonight*. |

---

## What "done" looks like at sunrise

Upload a PhonePe export → transactions parsed at a measured rate with unparsed rows queued, not lost → 4–8 labeled clusters with a silhouette you can defend and a stability number → a scatter you can click into, a trend chart, a filterable table → five plain-language insights about last month → a Re-cluster button that produces a new immutable run.

Phases 1–6 of the PRD, thin but complete, and a `DATABASE_URL` away from Supabase.
