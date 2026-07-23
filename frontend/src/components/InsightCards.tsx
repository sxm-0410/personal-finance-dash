import type { Insight } from '../lib/api'
import { fmtINR } from '../lib/api'

const sevColor: Record<string, string> = {
  warn: 'var(--warn)',
  info: 'var(--series-1)',
}

export default function InsightCards({ insights }: { insights: Insight[] }) {
  if (!insights.length) {
    return (
      <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
        No insights yet — upload at least two months of data and re-cluster.
      </p>
    )
  }
  return (
    <div className="flex flex-col gap-2">
      {insights.map((i) => (
        <div
          key={i.id}
          className="flex items-start gap-3 rounded-lg border p-3"
          style={{ background: 'var(--surface-2)' }}
        >
          <span
            className="mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full"
            style={{ background: sevColor[i.severity] ?? 'var(--text-muted)' }}
            aria-label={i.severity}
          />
          <div className="min-w-0 flex-1">
            <p className="text-sm" style={{ color: 'var(--text-primary)' }}>
              {i.body}
            </p>
            <p className="mt-0.5 text-xs" style={{ color: 'var(--text-muted)' }}>
              {i.period_month} · {i.kind} · impact {fmtINR(i.impact_amount)}
            </p>
          </div>
        </div>
      ))}
    </div>
  )
}
