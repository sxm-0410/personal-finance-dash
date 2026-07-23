import { useEffect, useMemo, useState } from 'react'
import type { Transaction } from '../lib/api'
import { api, fmtINR } from '../lib/api'

interface Props {
  clusterIndex: number | null
  clusterLabel?: string
}

const KINDS = ['spend', 'self_transfer', 'income', 'refund']

export default function TransactionTable({ clusterIndex, clusterLabel }: Props) {
  const [rows, setRows] = useState<Transaction[]>([])
  const [kind, setKind] = useState<string>('spend')
  const [merchant, setMerchant] = useState('')
  const [anomalyOnly, setAnomalyOnly] = useState(false)
  const [sortDesc, setSortDesc] = useState(true)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    api
      .transactions({
        cluster_index: clusterIndex ?? undefined,
        txn_kind: kind || undefined,
        merchant: merchant || undefined,
        is_anomaly: anomalyOnly || undefined,
        limit: 500,
      })
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }, [clusterIndex, kind, merchant, anomalyOnly])

  const sorted = useMemo(
    () => [...rows].sort((a, b) => (sortDesc ? b.amount - a.amount : a.amount - b.amount)),
    [rows, sortDesc],
  )

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
        {clusterIndex !== null && (
          <span
            className="rounded-full px-2 py-1 text-xs"
            style={{ background: 'var(--surface-2)', color: 'var(--text-secondary)' }}
          >
            filtered: {clusterLabel ?? `cluster ${clusterIndex}`}
          </span>
        )}
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value)}
          className="rounded-md border px-2 py-1 text-xs"
          style={{ background: 'var(--surface-2)', color: 'var(--text-primary)' }}
        >
          <option value="">all kinds</option>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <input
          value={merchant}
          onChange={(e) => setMerchant(e.target.value)}
          placeholder="merchant…"
          className="rounded-md border px-2 py-1 text-xs"
          style={{ background: 'var(--surface-2)', color: 'var(--text-primary)' }}
        />
        <label className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-secondary)' }}>
          <input
            type="checkbox"
            checked={anomalyOnly}
            onChange={(e) => setAnomalyOnly(e.target.checked)}
          />
          anomalies only
        </label>
        <span className="ml-auto text-xs" style={{ color: 'var(--text-muted)' }}>
          {loading ? 'loading…' : `${sorted.length} rows`}
        </span>
      </div>

      <div className="max-h-[420px] overflow-auto rounded-lg border">
        <table className="w-full text-left text-sm">
          <thead
            className="sticky top-0"
            style={{ background: 'var(--surface-2)', color: 'var(--text-secondary)' }}
          >
            <tr>
              <th className="px-3 py-2 font-medium">Date</th>
              <th className="px-3 py-2 font-medium">Merchant</th>
              <th className="px-3 py-2 font-medium">Kind</th>
              <th
                className="cursor-pointer px-3 py-2 text-right font-medium"
                onClick={() => setSortDesc((s) => !s)}
              >
                Amount {sortDesc ? '↓' : '↑'}
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((t) => (
              <tr key={t.id} style={{ borderTop: '1px solid var(--border)' }}>
                <td className="px-3 py-2" style={{ color: 'var(--text-muted)' }}>
                  {new Date(t.txn_date).toLocaleDateString('en-IN')}
                </td>
                <td className="px-3 py-2" style={{ color: 'var(--text-primary)' }}>
                  {t.counterparty_normalized}
                </td>
                <td className="px-3 py-2">
                  <span
                    className="rounded px-1.5 py-0.5 text-xs"
                    style={{ background: 'var(--surface-0)', color: 'var(--text-secondary)' }}
                  >
                    {t.txn_kind}
                  </span>
                </td>
                <td
                  className="px-3 py-2 text-right tabular-nums"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {fmtINR(t.amount)}
                </td>
              </tr>
            ))}
            {!loading && sorted.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-8 text-center" style={{ color: 'var(--text-muted)' }}>
                  No transactions match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
