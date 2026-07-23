import { useCallback, useEffect, useState } from 'react'
import Header from './components/Header'
import ClusterScatter from './components/ClusterScatter'
import SpendOverTime from './components/SpendOverTime'
import TransactionTable from './components/TransactionTable'
import InsightCards from './components/InsightCards'
import type { Cluster, Insight, Run, ScatterPoint, SpendOverTime as SOT } from './lib/api'
import { api } from './lib/api'

function Card({ title, subtitle, children }: {
  title: string
  subtitle?: string
  children: React.ReactNode
}) {
  return (
    <section className="rounded-xl border p-4" style={{ background: 'var(--surface-1)' }}>
      <div className="mb-3">
        <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          {title}
        </h2>
        {subtitle && (
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {subtitle}
          </p>
        )}
      </div>
      {children}
    </section>
  )
}

export default function App() {
  const [run, setRun] = useState<Run | null>(null)
  const [clusters, setClusters] = useState<Cluster[]>([])
  const [points, setPoints] = useState<ScatterPoint[]>([])
  const [spend, setSpend] = useState<SOT | null>(null)
  const [insights, setInsights] = useState<Insight[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [hasData, setHasData] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [runs, cl, pts, sot, ins] = await Promise.all([
        api.runs().catch(() => []),
        api.clusters().catch(() => []),
        api.points().catch(() => []),
        api.spendOverTime().catch(() => ({ months: [], series: [] }) as SOT),
        api.insights().catch(() => []),
      ])
      setRun(runs[0] ?? null)
      setClusters(cl)
      setPoints(pts)
      setSpend(sot)
      setInsights(ins)
      setHasData(cl.length > 0)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const selectedLabel = clusters.find((c) => c.cluster_index === selected)?.label

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <Header run={run} onChanged={load} />

      {!hasData && !loading ? (
        <div
          className="rounded-xl border p-10 text-center"
          style={{ background: 'var(--surface-1)', color: 'var(--text-secondary)' }}
        >
          <p className="text-lg font-medium" style={{ color: 'var(--text-primary)' }}>
            No clustering run yet
          </p>
          <p className="mt-1 text-sm">
            Upload a PhonePe CSV or PDF statement to discover your spending clusters.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card
            title="Spending clusters"
            subtitle="Each point is a transaction, placed by PCA of its behavioral features. Click a cluster to filter."
          >
            <ClusterScatter
              points={points}
              clusters={clusters}
              explainedVariance={run?.metrics_json?.pca_explained_variance}
              selected={selected}
              onSelect={setSelected}
            />
          </Card>

          <Card title="Spend by cluster over time" subtitle="Monthly totals, stacked by cluster.">
            {spend && spend.months.length > 0 ? (
              <SpendOverTime data={spend} selected={selected} />
            ) : (
              <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                Not enough monthly data yet.
              </p>
            )}
          </Card>

          <Card title="Insights" subtitle="Top changes this period, ranked by rupee impact.">
            <InsightCards insights={insights} />
          </Card>

          <Card title="Transactions" subtitle="Filterable. Click a cluster above to scope this table.">
            <TransactionTable clusterIndex={selected} clusterLabel={selectedLabel} />
          </Card>
        </div>
      )}
    </div>
  )
}
