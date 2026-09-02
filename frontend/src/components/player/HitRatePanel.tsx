import clsx from 'clsx'
import type { HitRate, ProjectionResponse } from '../../api/types'
import { statLabel } from '../../lib/statLabels'

const WINDOW_LABELS: Record<string, string> = {
  last_3: 'Last 3',
  last_5: 'Last 5',
  last_10: 'Last 10',
  season: 'This season',
  career: 'Career',
}

function toneFor(rate: number) {
  if (rate >= 0.6) return 'text-over'
  if (rate <= 0.4) return 'text-under'
  return 'text-warn'
}

/**
 * How often the player has actually cleared this line.
 *
 * Deliberately separate from the model panels: this is a count of games that
 * happened, with no assumptions in it at all. Where it disagrees sharply with
 * the projection - a career 39% against a season 75%, say - that gap is the
 * story, usually a change in role rather than noise.
 */
export function HitRatePanel({ result }: { result: ProjectionResponse }) {
  const rates: HitRate[] = result.hit_rates ?? []
  if (rates.length === 0) return null

  const career = rates.find((r) => r.window === 'career')
  const season = rates.find((r) => r.window === 'season')
  const divergence =
    career && season && season.games >= 3 ? Math.abs(season.rate - career.rate) : 0

  return (
    <div className="rounded-2xl border border-border bg-surface p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-text-muted">
          Times cleared {result.line}
        </h3>
        <span className="text-xs text-text-faint">{statLabel(result.stat)}</span>
      </div>
      <p className="mt-1 text-xs text-text-faint">
        Actual games, counted from the log — not a model output.
      </p>

      <ul className="mt-4 space-y-3">
        {rates.map((r) => (
          <li key={r.window}>
            <div className="flex items-center justify-between gap-3 text-xs">
              <span className="text-text-muted">{WINDOW_LABELS[r.window] ?? r.window}</span>
              <span className="shrink-0 tabular text-text-muted">
                <span className={clsx('font-bold', toneFor(r.rate))}>{r.hits}</span>
                <span className="text-text-faint">/{r.games}</span>
                <span className={clsx('ml-2 font-semibold', toneFor(r.rate))}>
                  {(r.rate * 100).toFixed(0)}%
                </span>
              </span>
            </div>
            <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-3">
              <div
                className={clsx(
                  'h-full rounded-full transition-all duration-500',
                  r.rate >= 0.6 ? 'bg-over' : r.rate <= 0.4 ? 'bg-under' : 'bg-warn',
                )}
                style={{ width: `${Math.max(r.rate * 100, 1)}%` }}
              />
            </div>
            <p className="mt-1 text-[11px] text-text-faint">averaged {r.average.toFixed(1)}</p>
          </li>
        ))}
      </ul>

      {divergence >= 0.2 && season && career && (
        <p className="mt-4 rounded-lg bg-surface-2 px-3 py-2 text-[11px] leading-relaxed text-text-muted">
          This season ({(season.rate * 100).toFixed(0)}%) is well clear of the career mark (
          {(career.rate * 100).toFixed(0)}%) — usually a sign the player's role has changed, so
          the older games may not say much about the current one.
        </p>
      )}
    </div>
  )
}
