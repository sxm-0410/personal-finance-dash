import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import type { SpendOverTime as SOT } from '../lib/api'
import { fmtINR } from '../lib/api'
import { clusterColor, resolveColor } from '../lib/colors'

interface Props {
  data: SOT
  selected: number | null
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function TooltipBox({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div
      style={{ background: 'var(--surface-2)', borderColor: 'var(--border)' }}
      className="rounded-lg border px-3 py-2 text-xs shadow-lg"
    >
      <div className="mb-1 font-semibold" style={{ color: 'var(--text-primary)' }}>
        {label}
      </div>
      {payload
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        .filter((p: any) => p.value > 0)
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        .map((p: any) => (
          <div key={p.name} className="flex items-center gap-2">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: p.color }}
            />
            <span style={{ color: 'var(--text-secondary)' }}>{p.name}</span>
            <span className="ml-auto" style={{ color: 'var(--text-primary)' }}>
              {fmtINR(p.value)}
            </span>
          </div>
        ))}
    </div>
  )
}

export default function SpendOverTime({ data, selected }: Props) {
  // Reshape to [{ month, [label]: value }]
  const rows = data.months.map((m, i) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const row: any = { month: m }
    for (const s of data.series) row[s.label] = s.values[i]
    return row
  })

  return (
    <ResponsiveContainer width="100%" height={320}>
      <AreaChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
        <defs>
          {data.series.map((s) => {
            const c = resolveColor(clusterColor(s.cluster_index))
            return (
              <linearGradient
                key={s.cluster_index}
                id={`g${s.cluster_index}`}
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop offset="0%" stopColor={c} stopOpacity={0.55} />
                <stop offset="100%" stopColor={c} stopOpacity={0.08} />
              </linearGradient>
            )
          })}
        </defs>
        <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
        <XAxis
          dataKey="month"
          tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
          tickLine={false}
          tickFormatter={(v) => (v >= 1000 ? `${v / 1000}k` : `${v}`)}
        />
        <Tooltip content={<TooltipBox />} />
        {data.series.map((s) => {
          const c = resolveColor(clusterColor(s.cluster_index))
          const dim = selected !== null && s.cluster_index !== selected
          return (
            <Area
              key={s.cluster_index}
              type="monotone"
              dataKey={s.label}
              stackId="1"
              stroke={c}
              strokeWidth={2}
              fill={`url(#g${s.cluster_index})`}
              fillOpacity={dim ? 0.15 : 1}
              strokeOpacity={dim ? 0.3 : 1}
            />
          )
        })}
      </AreaChart>
    </ResponsiveContainer>
  )
}
