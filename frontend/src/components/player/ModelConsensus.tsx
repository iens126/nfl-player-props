import clsx from 'clsx'
import type { ProjectionResponse } from '../../api/types'

const MODEL_NAMES: Record<string, string> = {
  ensemble: 'Ensemble',
  lognormal: 'Lognormal',
  negbin: 'Neg. binomial',
  empirical: 'Empirical',
  triangular: 'Triangular MC',
}

const MODEL_BLURBS: Record<string, string> = {
  ensemble: "Blends the parametric shape with the player's own game history",
  lognormal: 'Continuous, right-skewed yardage with a spike at zero',
  negbin: 'Discrete counting stats (receptions, carries, TDs)',
  empirical: "The player's actual games, smoothed — assumes no shape",
  triangular: 'The original method: samples a triangle over the last games',
}

/**
 * Each model's read on the same line.
 *
 * When the models cluster, the number is robust to the assumed distribution;
 * when they spread out, the answer is being driven by modelling choices rather
 * than by the player's data, which is worth knowing before trusting it.
 */
export function ModelConsensus({ result }: { result: ProjectionResponse }) {
  const entries = Object.entries(result.alternatives)
  if (entries.length === 0) return null

  const probs = entries.map(([, v]) => v)
  const spread = Math.max(...probs) - Math.min(...probs)
  const agreement = spread < 0.08 ? 'strong' : spread < 0.18 ? 'moderate' : 'weak'

  const agreementCopy = {
    strong: 'The models agree closely — this read is robust to the assumed distribution.',
    moderate: 'The models mostly agree, with some sensitivity to the assumed distribution.',
    weak: 'The models disagree — this line sits where the assumed distribution matters a lot.',
  }[agreement]

  const agreementTone = {
    strong: 'text-over',
    moderate: 'text-warn',
    weak: 'text-under',
  }[agreement]

  return (
    <div className="rounded-2xl border border-border bg-surface p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-text-muted">
          Model consensus
        </h3>
        <span className={clsx('text-xs font-semibold uppercase tracking-wide', agreementTone)}>
          {agreement} agreement
        </span>
      </div>
      <p className="mt-1 text-xs text-text-faint">{agreementCopy}</p>

      <ul className="mt-4 space-y-2.5">
        {entries.map(([key, prob]) => {
          const isActive = key === result.model
          return (
            <li key={key} title={MODEL_BLURBS[key] ?? ''}>
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className={clsx('truncate', isActive ? 'font-bold text-text' : 'text-text-muted')}>
                  {MODEL_NAMES[key] ?? key}
                  {isActive && <span className="ml-1.5 text-[10px] font-semibold text-accent-soft">IN USE</span>}
                </span>
                <span className={clsx('tabular shrink-0 font-semibold', isActive ? 'text-text' : 'text-text-muted')}>
                  {(prob * 100).toFixed(1)}%
                </span>
              </div>
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-3">
                <div
                  className={clsx(
                    'h-full rounded-full transition-all duration-500',
                    isActive ? 'bg-accent' : 'bg-text-faint/45',
                  )}
                  style={{ width: `${Math.max(prob * 100, 1)}%` }}
                />
              </div>
            </li>
          )
        })}
      </ul>
      <p className="mt-3 text-[11px] leading-relaxed text-text-faint">
        Probability of going <span className="font-semibold text-text-muted">over</span> {result.line}, under each
        model's assumptions.
      </p>
    </div>
  )
}
