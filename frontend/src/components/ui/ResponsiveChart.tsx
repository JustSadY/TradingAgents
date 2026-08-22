import { ResponsiveContainer } from 'recharts'
import type { ComponentProps } from 'react'

type ResponsiveChartProps = ComponentProps<typeof ResponsiveContainer>

/**
 * A first-render size that recharts does not complain about.
 *
 * `ResponsiveContainer` starts at `{ width: -1, height: -1 }` and asserts on
 * every render where neither axis is positive — "The width(-1) and height(-1)
 * of chart should be greater than 0". With a percentage size that is every
 * mount, before its ResizeObserver has measured the box, and recharts' ESM
 * build ships the warning enabled in production builds too, so the console
 * filled up with it on the dashboard and every other chart page.
 *
 * A positive height satisfies the assertion. The width stays unmeasured, which
 * is what actually gates rendering: the container still draws nothing until it
 * knows its real box, so no chart is ever painted at a guessed size.
 */
const UNMEASURED = { width: -1, height: 1 }

export function ResponsiveChart(props: ResponsiveChartProps) {
  return <ResponsiveContainer initialDimension={UNMEASURED} {...props} />
}

export default ResponsiveChart
