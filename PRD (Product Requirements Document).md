

## Personal Finance Dashboard with Spending Clusters

## 1. Overview

A personal analytics dashboard that ingests UPI transaction history (starting with PhonePe exports) and uses unsupervised machine learning to group transactions into natural "spending clusters" — patterns discovered from the data itself rather than manually assigned categories. The dashboard visualizes these clusters and surfaces plain-language insights about spending behavior over time.

This is primarily a personal tool and a portfolio/resume piece demonstrating applied ML (clustering, feature engineering) combined with full-stack delivery (FastAPI, Supabase, React).

---

## 2. Problem Statement

Manually categorizing expenses is tedious and categories are often too coarse ("Food" lumps together a ₹40 tea and a ₹2,000 dinner) or inconsistently applied. There's no easy way to see _natural_ spending patterns — recurring subscriptions, impulse purchases, big one-off buys — without either a lot of manual tagging or a system that discovers these groupings automatically.

---

## 3. Goals and Non-Goals

**Goals**

- Automatically ingest and clean UPI transaction data (PDF export → structured records)
- Discover natural spending clusters using unsupervised ML, without relying on pre-defined categories
- Visualize clusters and trends in an interactive dashboard
- Surface human-readable insights (e.g. "your recurring-subscription cluster grew 18% this month")
- Ship a working end-to-end product usable with real personal data

**Non-Goals (v1)**

- Multi-user / multi-tenant support (this is single-user to start)
- Direct bank/API integration (e.g. Plaid-style live account linking) — out of scope until UPI-only pipeline is proven
- Investment or net-worth tracking — spending only
- Budgeting/goal-setting features — reserved for a later version

---

## 4. Target User

Primary: Self, tracking personal UPI spend. Secondary (future): any individual UPI user who wants automatic pattern discovery instead of manual budgeting apps — relevant if this is extended into a shareable product later.

---

## 5. User Stories

- As a user, I want to upload my PhonePe statement so the app can extract my transactions automatically.
- As a user, I want my transactions grouped into behavioral clusters without me manually tagging each one.
- As a user, I want to see which clusters are growing or shrinking month over month.
- As a user, I want to click into a cluster and see the actual transactions inside it.
- As a user, I want the dashboard to flag unusually large or unusual transactions.

---

## 6. Functional Requirements

|Area|Requirement|
|---|---|
|Data ingestion|Parse PhonePe PDF statement exports into structured rows (date, amount, direction, counterparty, reference/UTR)|
|Data cleaning|Deduplicate, normalize merchant/counterparty names, strip currency formatting, handle self-transfers separately from spend|
|Feature engineering|Derive amount (log-scaled), frequency, recency, day-of-week/month, recurring-payment flag|
|Clustering|Run K-means (primary) on the feature set; run DBSCAN as a secondary pass for outlier/anomaly detection|
|Cluster labeling|Auto-generate a human-readable label per cluster based on its dominant characteristics (e.g. "small frequent purchases", "recurring bills")|
|Insights|Generate plain-language monthly summaries per cluster (growth/shrinkage, new merchants appearing)|
|Storage|Persist raw transactions, engineered features, and cluster assignments in Supabase|
|API|FastAPI endpoints: `/transactions`, `/clusters`, `/insights`, `/upload`|
|Dashboard|React + Tailwind + shadcn/ui frontend: cluster scatter plot (PCA-reduced), spend-by-cluster-over-time chart, filterable transaction table|
|Re-clustering|Ability to re-run clustering as new data is added (manual trigger in v1, scheduled later)|

---

## 7. Non-Functional Requirements

- **Privacy:** this is financial data — even as a personal project, avoid storing raw PDFs or unmasked account/UPI IDs longer than necessary; consider basic encryption at rest in Supabase.
- **Performance:** clustering should complete in well under a few seconds for a single year of personal transaction volume (a few thousand rows at most) — not a performance-critical system.
- **Reliability:** PDF parsing should degrade gracefully (flag unparseable rows for manual review rather than silently dropping them).
- **Portability:** pipeline should not be tightly coupled to PhonePe's PDF format alone — structure the parser so a Google Pay or Paytm export could plug in later with a different adapter.

---

## 8. System Architecture

**Pipeline:** PhonePe PDF export → parser/cleaner → feature engineering → clustering engine (scikit-learn) → Supabase (storage) → FastAPI (serving) → React dashboard (visualization).

- **ML layer:** Python, pandas, scikit-learn (`StandardScaler`, `KMeans`, `DBSCAN`), optionally UMAP/PCA for 2D visualization
- **Backend:** FastAPI, serving cluster and insight data as JSON
- **Database:** Supabase (Postgres) — transactions table, clusters table, cluster_assignments table
- **Frontend:** React, Tailwind, shadcn/ui, recharts for visualization

---

## 9. Data Model (draft)

**transactions** `id, date, amount, direction (debit/credit), counterparty_raw, counterparty_normalized, reference_id, source_app, created_at`

**features** (derived, keyed to transaction id) `id, transaction_id, log_amount, day_of_week, day_of_month, is_recurring, recency_days, frequency_score`

**clusters** `id, run_id, label, centroid_summary, created_at`

**cluster_assignments** `transaction_id, cluster_id, run_id, distance_to_centroid`

---

## 10. Success Metrics

- Clusters are interpretable — each one has a clear, describable theme when manually reviewed
- Silhouette score above a reasonable threshold (rough guide: >0.3) indicating real separation, not arbitrary grouping
- At least 90% of transactions successfully parsed from the PDF without manual correction
- Dashboard loads and renders cluster visualization in under 2 seconds for a year of data

---

## 11. Milestones & Phased Rollout

|Phase|Deliverable|
|---|---|
|1|PhonePe PDF → structured transaction dataset (real or synthetic)|
|2|Cleaning + feature engineering pipeline in a notebook|
|3|K-means clustering with validated k, plus DBSCAN outlier pass|
|4|FastAPI backend + Supabase schema live|
|5|React dashboard: cluster scatter plot, trend chart, transaction table|
|6 (stretch)|Scheduled re-clustering, auto-generated monthly insights|

---

## 12. Challenges We Might Face

**Data access & format**

- PhonePe exports as PDF, not CSV — every transaction needs to be extracted via PDF parsing, which is more brittle than reading a clean tabular file
- The PDF may be password-protected (registered mobile number), adding a decryption step before parsing
- In-app history is typically capped around a year, limiting how much historical data is available without a support request
- If the PDF layout changes in a future PhonePe app update, the parser may break silently

**Data quality**

- Counterparty names are inconsistent (e.g. the same merchant appearing as slightly different strings across transactions) and will need fuzzy matching or manual mapping
- Self-transfers (e.g. moving money to your own linked accounts) can distort spend totals if not filtered out separately from actual spending
- Small sample size (a personal dataset, not thousands of users) means clusters can be sensitive to a handful of unusual transactions

**Feature engineering & clustering**

- Raw amount is heavily right-skewed — without log-scaling, a few large transactions (rent) will dominate distance calculations and drown out smaller patterns
- Choosing the right number of clusters (k) is somewhat subjective; elbow/silhouette methods give guidance but not a single correct answer
- With a small personal dataset, K-means results can be unstable — a re-run with slightly different data can shift cluster boundaries meaningfully
- Curse of dimensionality: too many engineered features relative to the number of transactions can make distances less meaningful — feature selection will matter

**Interpretability**

- Clusters produced by an algorithm don't come with human-readable names — auto-labeling logic (or manual review) is needed to make them useful rather than just "Cluster 0, 1, 2"
- Explaining _why_ a transaction landed in a given cluster to a non-technical viewer (future self, or others if this becomes shareable) takes deliberate UX work, not just a scatter plot

**Privacy & security**

- This is real financial data — even for a solo project, storing it in Supabase means thinking about encryption, access control, and not leaving raw statements or UPI IDs exposed
- If this ever becomes a multi-user product, data handling requirements get significantly stricter

**Scope & bandwidth**

- As a solo project running alongside coursework and GRE prep, the biggest practical risk is scope creep — the temptation to build the "perfect" pipeline before shipping something end-to-end. Time-boxing each phase (per the milestones above) helps keep this shippable rather than open-ended.

---

## 13. Open Questions

- Should clustering run on transactions (Option A, this doc's assumption) or on time periods/days (Option B)? PRD assumes Option A.
- Should this stay strictly personal, or is a multi-user version worth designing for from the start (affects the data model and auth requirements)?
- Is PhonePe the only data source, or should Google Pay / Paytm exports be supported from day one?

---

## 14. Appendix: Tech Stack Summary

- **ML/Data:** Python, pandas, scikit-learn, PCA/UMAP for visualization
- **Backend:** FastAPI
- **Database:** Supabase (Postgres)
- **Frontend:** React, Tailwind, shadcn/ui, recharts