import {
  Bar,
  CartesianGrid,
  ComposedChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import clsx from 'clsx'
import type { ChartResponse } from '../../api/types'
import type { MatchupColors } from '../../lib/teamColors'
import { statLabel } from '../../lib/statLabels'

export type ChartRange = '3' | '5' | '10' | 'season' | 'career'

const RANGE_OPTIONS: { value: ChartRange; label: string }[] = [
  { value: '3', label: 'Last 3' },
  { value: '5', label: 'Last 5' },
  { value: '10', label: 'Last 10' },
  { value: 'season', label: 'Season' },
  { value: 'career', label: 'Career' },
]

export function PerformanceChart({
  chart,
  range,
  onRangeChange,
  line,
  opponentAbbr,
  playerAbbr,
  colors,
}: {
  chart: ChartResponse
  range: ChartRange
  onRangeChange: (r: ChartRange) => void
  line: number | null
  opponentAbbr: string
  playerAbbr: string
  colors: MatchupColors
}) {
  const data = chart.weeks.map((w) => ({
    week: w.label ?? `W${w.week}`,
    opponent: w.opponent,
    player: w.player_value,
    defense: w.defense_allowed,
  }))

  // Career labels ("'23 W12") are roughly twice as wide as in-season ones
  // ("W12"), so the number of ticks that fit depends on the label, not just
  // the point count. Aim for a tick roughly every 70px of plot width.
  const longestLabel = data.reduce((max, d) => Math.max(max, d.week.length), 0)
  const maxTicks = Math.max(3, Math.floor(60 / Math.max(longestLabel, 1)))
  const tickInterval =
    data.length > maxTicks ? Math.ceil(data.length / maxTicks) - 1 : ('preserveStartEnd' as const)

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-xs text-text-muted">
          <span className="inline-flex h-2.5 w-2.5 rounded-sm" style={{ background: colors.player }} />
          <span>
            <span className="font-semibold text-text">{playerAbbr}</span> {statLabel(chart.stat)}
          </span>
          <span className="mx-1 text-text-faint">·</span>
          <span className="inline-flex h-2.5 w-2.5 rounded-sm" style={{ background: colors.defense }} />
          <span>
            <span className="font-semibold text-text">{opponentAbbr}</span> allowed
          </span>
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
          <ComposedChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
            <XAxis
              dataKey="week"
              tick={{ fill: 'var(--color-text-faint)', fontSize: 12 }}
              axisLine={{ stroke: 'var(--color-border)' }}
              tickLine={false}
              interval={tickInterval}
            />
            {/* Wide enough for three-digit yardage totals - a narrower axis clips them. */}
            <YAxis tick={{ fill: 'var(--color-text-faint)', fontSize: 12 }} axisLine={false} tickLine={false} width={46} />
            <Tooltip
              content={(props) => <ChartTooltip {...props} stat={chart.stat} colors={colors} />}
              cursor={{ fill: 'color-mix(in srgb, var(--color-text) 6%, transparent)' }}
            />
            <Bar dataKey="player" name={`${playerAbbr} ${statLabel(chart.stat)}`} fill={colors.player} radius={[4, 4, 0, 0]} maxBarSize={28} />
            <Bar dataKey="defense" name={`${opponentAbbr} allowed`} fill={colors.defense} fillOpacity={0.55} radius={[4, 4, 0, 0]} maxBarSize={28} />
            {chart.player_average !== null && (
              <ReferenceLine
                y={chart.player_average}
                stroke="var(--color-text-faint)"
                strokeDasharray="4 4"
                label={{ value: 'Avg', position: 'insideTopLeft', offset: 10, fill: 'var(--color-text-faint)', fontSize: 11 }}
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
  colors: MatchupColors
}

function ChartTooltip({ active, payload, label, stat, colors }: ChartTooltipProps) {
  const row = payload?.[0]?.payload
  if (!active || !row) return null

  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-xl">
      <p className="font-semibold text-text">
        {label} {row.opponent ? `vs ${row.opponent}` : ''}
      </p>
      <p className="mt-1 flex items-center gap-1.5 text-text-muted">
        <span className="inline-flex h-2 w-2 rounded-sm" style={{ background: colors.player }} />
        {statLabel(stat)}: <span className="tabular font-semibold text-text">{row.player ?? '—'}</span>
      </p>
      <p className="flex items-center gap-1.5 text-text-muted">
        <span className="inline-flex h-2 w-2 rounded-sm" style={{ background: colors.defense }} />
        Defense allowed: <span className="tabular font-semibold text-text">{row.defense ?? '—'}</span>
      </p>
    </div>
  )
}
