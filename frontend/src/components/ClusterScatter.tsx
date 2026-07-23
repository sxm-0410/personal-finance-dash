import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import type { Cluster, ScatterPoint } from '../lib/api'
import { fmtINR } from '../lib/api'
import { clusterColor, resolveColor } from '../lib/colors'

interface Props {
  points: ScatterPoint[]
  clusters: Cluster[]
  explainedVariance?: number[]
  selected: number | null
  onSelect: (c: number | null) => void
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function AnomalyRing(props: any) {
  const { cx, cy } = props
  if (cx == null || cy == null) return <g />
  return (
    <circle
      cx={cx}
      cy={cy}
      r={7}
      fill="none"
      stroke={resolveColor('var(--anomaly)')}
      strokeWidth={2}
    />
  )
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function TooltipBox({ active, payload }: any) {
  if (!active || !payload?.length) return null
  const p: ScatterPoint = payload[0].payload
  return (
    <div
      style={{ background: 'var(--surface-2)', borderColor: 'var(--border)' }}
      className="rounded-lg border px-3 py-2 text-xs shadow-lg"
    >
      <div className="font-semibold" style={{ color: 'var(--text-primary)' }}>
        {p.counterparty}
      </div>
      <div style={{ color: 'var(--text-secondary)' }}>
        {fmtINR(p.amount)} · {new Date(p.txn_date).toLocaleDateString('en-IN')}
      </div>
      {p.is_anomaly && (
        <div className="mt-1" style={{ color: 'var(--anomaly)' }}>
          ⚠ {p.anomaly_reason}
        </div>
      )}
    </div>
  )
}

export default function ClusterScatter({
  points,
  clusters,
  explainedVariance,
  selected,
  onSelect,
}: Props) {
  const normal = points.filter((p) => !p.is_anomaly)
  const anomalies = points.filter((p) => p.is_anomaly)
  const dim = (p: ScatterPoint) => selected !== null && p.cluster_index !== selected

  const axisLabel = (i: number) =>
    explainedVariance?.[i] != null
      ? `PC${i + 1} (${(explainedVariance[i] * 100).toFixed(0)}% var)`
      : `PC${i + 1}`

  return (
    <div>
      <ResponsiveContainer width="100%" height={360}>
        <ScatterChart margin={{ top: 8, right: 16, bottom: 24, left: 8 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" />
          <XAxis
            type="number"
            dataKey="pca_x"
            name={axisLabel(0)}
            tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
            label={{
              value: axisLabel(0),
              position: 'bottom',
              fill: 'var(--text-secondary)',
              fontSize: 11,
            }}
          />
          <YAxis
            type="number"
            dataKey="pca_y"
            name={axisLabel(1)}
            tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
            label={{
              value: axisLabel(1),
              angle: -90,
              position: 'left',
              fill: 'var(--text-secondary)',
              fontSize: 11,
            }}
          />
          <ZAxis range={[36, 36]} />
          <Tooltip content={<TooltipBox />} cursor={{ strokeDasharray: '3 3' }} />
          <Scatter
            data={normal}
            isAnimationActive={false}
            onClick={(d: unknown) =>
              onSelect((d as ScatterPoint).cluster_index === selected
                ? null
                : (d as ScatterPoint).cluster_index)
            }
          >
            {normal.map((p) => (
              <Cell
                key={p.transaction_id}
                fill={resolveColor(clusterColor(p.cluster_index))}
                fillOpacity={dim(p) ? 0.12 : 0.8}
                stroke="var(--surface-1)"
                strokeWidth={1}
              />
            ))}
          </Scatter>
          {/* Anomalies as hollow rings — shape encodes the flag, not color alone. */}
          <Scatter data={anomalies} shape={<AnomalyRing />} isAnimationActive={false} />
        </ScatterChart>
      </ResponsiveContainer>

      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
        {clusters.map((c) => (
          <button
            key={c.id}
            onClick={() =>
              onSelect(c.cluster_index === selected ? null : c.cluster_index)
            }
            className="flex items-center gap-1.5 rounded-full px-2 py-1 transition"
            style={{
              background:
                selected === c.cluster_index ? 'var(--surface-2)' : 'transparent',
              color: 'var(--text-secondary)',
              opacity: selected !== null && selected !== c.cluster_index ? 0.5 : 1,
            }}
          >
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ background: resolveColor(clusterColor(c.cluster_index)) }}
            />
            {c.label}
          </button>
        ))}
        <span className="flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
          <span
            className="inline-block h-3 w-3 rounded-full border-2"
            style={{ borderColor: 'var(--anomaly)' }}
          />
          anomaly
        </span>
      </div>
    </div>
  )
}
