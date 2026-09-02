import clsx from 'clsx'
import type { ProjectionResponse } from '../../api/types'
import { statLabel } from '../../lib/statLabels'

export function OverUnderPanel({ result }: { result: ProjectionResponse }) {
  const overPct = Math.round(result.prob_over * 1000) / 10
  const underPct = Math.round(result.prob_under * 1000) / 10
  const lean: 'over' | 'under' = result.prob_over >= result.prob_under ? 'over' : 'under'

  return (
    <div className="rounded-2xl border border-border bg-surface p-5 sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-text-faint">Model Projection</p>
          <p className="mt-1 text-4xl font-extrabold tabular tracking-tight text-text sm:text-5xl">
            {result.projection.toFixed(1)}
          </p>
          <p className="mt-1 text-xs text-text-faint">{statLabel(result.stat)} · estimated mean outcome</p>
        </div>
        <div className="text-right">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-text-faint">Prop Line</p>
          <p className="mt-1 text-2xl font-bold tabular text-text-muted">{result.line}</p>
        </div>
      </div>

      {/* segmented probability bar */}
      <div className="mt-6">
        <div className="flex h-3 w-full overflow-hidden rounded-full bg-surface-3">
          <div className="h-full bg-over transition-all duration-500" style={{ width: `${overPct}%` }} />
          <div className="h-full bg-under transition-all duration-500" style={{ width: `${underPct}%` }} />
        </div>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 sm:gap-4">
        <div
          className={clsx(
            'rounded-xl border p-4 transition-colors',
            lean === 'over' ? 'border-over/40 bg-over/10' : 'border-border bg-surface-2',
          )}
        >
          <p className="text-xs font-bold uppercase tracking-wider text-over">Over</p>
          <p className="mt-1 text-3xl font-extrabold tabular text-text">{overPct}%</p>
        </div>
        <div
          className={clsx(
            'rounded-xl border p-4 transition-colors',
            lean === 'under' ? 'border-under/40 bg-under/10' : 'border-border bg-surface-2',
          )}
        >
          <p className="text-xs font-bold uppercase tracking-wider text-under">Under</p>
          <p className="mt-1 text-3xl font-extrabold tabular text-text">{underPct}%</p>
        </div>
      </div>

      <p className="mt-4 text-xs leading-relaxed text-text-faint">
        {result.model_label} fitted to the player's last {result.window_games} games — weighted
        toward the most recent — then shifted {result.weight >= 0 ? '+' : ''}
        {result.weight.toFixed(1)} for the {result.opponent} matchup. This is a statistical estimate,
        not a guarantee.
      </p>
    </div>
  )
}
