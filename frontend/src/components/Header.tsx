import { useRef, useState } from 'react'
import type { Run } from '../lib/api'
import { api } from '../lib/api'

interface Props {
  run: Run | null
  onChanged: () => void
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div
      className="rounded-lg border px-3 py-2"
      style={{ background: 'var(--surface-2)' }}
    >
      <div className="text-lg font-semibold tabular-nums" style={{ color: 'var(--text-primary)' }}>
        {value}
      </div>
      <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
        {label}
      </div>
    </div>
  )
}

export default function Header({ run, onChanged }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  const toggleTheme = () => {
    const root = document.documentElement
    const dark =
      root.getAttribute('data-theme') === 'dark' ||
      (!root.getAttribute('data-theme') &&
        window.matchMedia('(prefers-color-scheme: dark)').matches)
    root.setAttribute('data-theme', dark ? 'light' : 'dark')
  }

  const onUpload = async (file: File) => {
    setBusy('Parsing…')
    setMsg(null)
    try {
      const stats = await api.upload(file)
      setMsg(
        `Parsed ${stats.parsed} (${(stats.parse_rate * 100).toFixed(0)}%), ` +
          `inserted ${stats.inserted}. Re-clustering…`,
      )
      setBusy('Clustering…')
      await api.recluster()
      onChanged()
      setMsg(`Done — imported ${stats.inserted} new transactions.`)
    } catch (e) {
      setMsg(`Error: ${(e as Error).message}`)
    } finally {
      setBusy(null)
    }
  }

  const onRecluster = async () => {
    setBusy('Clustering…')
    setMsg(null)
    try {
      await api.recluster()
      onChanged()
      setMsg('Re-clustered.')
    } catch (e) {
      setMsg(`Error: ${(e as Error).message}`)
    } finally {
      setBusy(null)
    }
  }

  return (
    <header className="mb-6">
      <div className="flex flex-wrap items-center gap-3">
        <div className="mr-auto">
          <h1 className="text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
            Spending Clusters
          </h1>
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
            Unsupervised patterns discovered from your UPI history
          </p>
        </div>

        <input
          ref={fileRef}
          type="file"
          accept=".csv,.pdf"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])}
        />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={!!busy}
          className="rounded-lg px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
          style={{ background: 'var(--series-1)' }}
        >
          Upload statement
        </button>
        <button
          onClick={onRecluster}
          disabled={!!busy}
          className="rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-50"
          style={{ background: 'var(--surface-2)', color: 'var(--text-primary)' }}
        >
          Re-cluster
        </button>
        <button
          onClick={toggleTheme}
          className="rounded-lg border px-3 py-2 text-sm"
          style={{ background: 'var(--surface-2)', color: 'var(--text-primary)' }}
          aria-label="Toggle theme"
        >
          ◐
        </button>
      </div>

      {(busy || msg) && (
        <p className="mt-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
          {busy ?? msg}
        </p>
      )}

      {run && (
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-6">
          <Stat label="clusters (k)" value={String(run.k)} />
          <Stat
            label="silhouette"
            value={run.silhouette != null ? run.silhouette.toFixed(2) : '—'}
          />
          <Stat
            label="stability (ARI)"
            value={run.mean_ari != null ? run.mean_ari.toFixed(2) : '—'}
          />
          <Stat label="transactions" value={String(run.n_transactions)} />
          <Stat label="anomalies" value={String(run.metrics_json?.n_anomalies ?? 0)} />
          <Stat label="algorithm" value={run.algo} />
        </div>
      )}
    </header>
  )
}
