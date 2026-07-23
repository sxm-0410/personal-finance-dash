// API client + shared types. All paths are same-origin /api (Vite proxies to
// the FastAPI backend in dev).

export interface Cluster {
  id: string
  cluster_index: number
  label: string
  centroid_summary: {
    avg_amount: number
    merchant_frequency: number
    recurring_share: number
    amount_stability: number
  }
  n_transactions: number
  total_amount: number
}

export interface ScatterPoint {
  transaction_id: string
  pca_x: number
  pca_y: number
  amount: number
  counterparty: string
  txn_date: string
  cluster_index: number
  is_anomaly: boolean
  anomaly_reason: string | null
}

export interface Transaction {
  id: string
  txn_date: string
  amount: number
  direction: string
  txn_kind: string
  counterparty_normalized: string
  counterparty_raw: string
  parse_confidence: number
}

export interface Insight {
  id: string
  period_month: string
  kind: string
  severity: string
  body: string
  impact_amount: number
}

export interface Run {
  id: string
  created_at: string
  algo: string
  k: number
  silhouette: number | null
  mean_ari: number | null
  n_transactions: number
  metrics_json: {
    k_sweep?: { k: number; inertia: number; silhouette: number }[]
    pca_explained_variance?: number[]
    n_anomalies?: number
  }
}

export interface SpendOverTime {
  months: string[]
  series: { cluster_index: number; label: string; values: number[] }[]
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export const api = {
  runs: () => get<Run[]>('/runs?latest=true'),
  clusters: () => get<Cluster[]>('/clusters'),
  points: () => get<ScatterPoint[]>('/clusters/points'),
  spendOverTime: () => get<SpendOverTime>('/spend-over-time'),
  insights: () => get<Insight[]>('/insights'),
  transactions: (params: Record<string, string | number | boolean | undefined>) => {
    const q = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== '') q.set(k, String(v))
    }
    return get<Transaction[]>(`/transactions?${q.toString()}`)
  },
  recluster: async (): Promise<Run> => {
    const res = await fetch('/api/recluster', { method: 'POST' })
    if (!res.ok) throw new Error((await res.json()).detail ?? 'recluster failed')
    return res.json()
  },
  upload: async (file: File, password?: string) => {
    const fd = new FormData()
    fd.append('file', file)
    if (password) fd.append('password', password)
    const res = await fetch('/api/upload', { method: 'POST', body: fd })
    if (!res.ok) throw new Error((await res.json()).detail ?? 'upload failed')
    return res.json()
  },
}

export const fmtINR = (n: number) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(n)
