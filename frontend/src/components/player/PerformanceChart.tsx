import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import clsx from 'clsx'
import type { ChartResponse } from '../../api/types'
import { statLabel } from '../../lib/statLabels'

export type ChartRange = '3' | '5' | '10' | 'season'

const RANGE_OPTIONS: { value: ChartRange; label: string }[] = [
  { value: '3', label: 'Last 3' },
  { value: '5', label: 'Last 5' },
  { value: '10', label: 'Last 10' },
  { value: 'season', label: 'Season' },
]

export function PerformanceChart({
  chart,
  range,
  onRangeChange,
  line,
  opponentAbbr,
}: {
  chart: ChartResponse
  range: ChartRange
  onRangeChange: (r: ChartRange) => void
  line: number | null
  opponentAbbr: string
}) {
  const data = chart.weeks.map((w) => ({
    week: `W${w.week}`,
    opponent: w.opponent,
    player: w.player_value,
    defense: w.defense_allowed,
  }))

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs text-text-faint">
          <span className="inline-flex h-2.5 w-2.5 rounded-sm bg-accent" /> {statLabel(chart.stat)}
          <span className="mx-1">·</span>
          <span className="inline-flex h-2.5 w-2.5 rounded-sm bg-cyan/60" /> {opponentAbbr} allowed
        </div>
        <div className="flex gap-1 rounded-lg bg-surface-2 p-1">
          {RANGE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => onRangeChange(opt.value)}
              className={clsx(
                'rounded-md px-2.5 py-1 text-xs font-semibold transition-colors',
                range === opt.value ? 'bg-accent text-white' : 'text-text-muted hover:text-text',
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="h-72 w-full sm:h-80">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
            <XAxis dataKey="week" tick={{ fill: 'var(--color-text-faint)', fontSize: 12 }} axisLine={{ stroke: 'var(--color-border)' }} tickLine={false} />
            <YAxis tick={{ fill: 'var(--color-text-faint)', fontSize: 12 }} axisLine={false} tickLine={false} width={40} />
            <Tooltip content={(props) => <ChartTooltip {...props} stat={chart.stat} />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
            <Bar dataKey="player" name={statLabel(chart.stat)} fill="var(--color-accent)" radius={[4, 4, 0, 0]} maxBarSize={28} />
            <Bar dataKey="defense" name={`${opponentAbbr} allowed`} fill="var(--color-cyan)" fillOpacity={0.35} radius={[4, 4, 0, 0]} maxBarSize={28} />
            {chart.player_average !== null && (
              <ReferenceLine
                y={chart.player_average}
                stroke="var(--color-text-faint)"
                strokeDasharray="4 4"
                label={{ value: 'Avg', position: 'insideTopLeft', fill: 'var(--color-text-faint)', fontSize: 11 }}
              />
            )}
            {line !== null && !Number.isNaN(line) && (
              <ReferenceLine
                y={line}
                stroke="var(--color-warn)"
                strokeWidth={2}
                strokeDasharray="6 3"
                label={{ value: `Line ${line}`, position: 'insideTopRight', fill: 'var(--color-warn)', fontSize: 11, fontWeight: 700 }}
              />
            )}
            <Legend
              wrapperStyle={{ fontSize: 12, color: 'var(--color-text-faint)' }}
              formatter={(value) => <span style={{ color: 'var(--color-text-muted)' }}>{value}</span>}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

interface ChartTooltipProps {
  active?: boolean
  label?: string | number
  payload?: readonly { payload?: { week: string; opponent: string | null; player: number | null; defense: number | null } }[]
  stat: string
}

function ChartTooltip({ active, payload, label, stat }: ChartTooltipProps) {
  const row = payload?.[0]?.payload
  if (!active || !row) return null

  return (
    <div className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-xs shadow-xl">
      <p className="font-semibold text-text">
        {label} {row.opponent ? `vs ${row.opponent}` : ''}
      </p>
      <p className="mt-1 text-text-muted">
        {statLabel(stat)}: <span className="tabular font-semibold text-accent-soft">{row.player ?? '—'}</span>
      </p>
      <p className="text-text-muted">
        Defense allowed: <span className="tabular font-semibold text-cyan">{row.defense ?? '—'}</span>
      </p>
    </div>
  )
}
