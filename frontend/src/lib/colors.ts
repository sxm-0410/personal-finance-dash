// Cluster color identity. One entity -> one hue, assigned in fixed order and
// keyed by cluster_index so it never repaints when filters change the visible
// set. Reads the CSS custom properties so light/dark stay in sync.

const SLOTS = 8

export function clusterColor(clusterIndex: number): string {
  const slot = (clusterIndex % SLOTS) + 1
  return `var(--series-${slot})`
}

// Resolve a CSS var to a concrete hex at call time (recharts needs real colors
// for some props). Falls back gracefully during SSR/first paint.
export function resolveColor(cssVar: string): string {
  if (typeof window === 'undefined') return '#2a78d6'
  const name = cssVar.replace('var(', '').replace(')', '').trim()
  const val = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim()
  return val || '#2a78d6'
}

export const anomalyColor = () => resolveColor('var(--anomaly)')
