import { ArrowTopRightOnSquareIcon, CpuChipIcon } from '@heroicons/react/24/outline'
import type { ModelInfo } from '../../api/types'

/**
 * What the selected model is, in plain language.
 *
 * For the trained model the "pays attention to" list is not editorial - it is
 * permutation importance measured on held-out games, so it reports what the
 * model actually leans on. The validation numbers are shown for the same
 * reason: a projection tool should make its own track record visible rather
 * than ask to be trusted.
 */
export function ModelInfoPanel({ info }: { info: ModelInfo | null }) {
  if (!info) return null
  const m = info.metrics

  return (
    <div className="rounded-2xl border border-border bg-surface p-5">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-xs font-bold uppercase tracking-wider text-text-muted">
          About this model
        </h3>
        {info.trained && (
          <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-accent/30 bg-accent/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-accent-soft">
            <CpuChipIcon className="h-3 w-3" />
            Trained
          </span>
        )}
      </div>

      {info.summary && (
        <p className="mt-2 text-xs leading-relaxed text-text-muted">{info.summary}</p>
      )}

      {info.attends_to.length > 0 && (
        <div className="mt-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-faint">
            {info.trained ? 'What it learned to rely on' : 'What it pays attention to'}
          </p>
          <ul className="mt-2 space-y-1.5">
            {info.attends_to.map((item) => (
              <li key={item} className="flex gap-2 text-xs text-text-muted">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}

      {info.importance.length > 0 && (
        <div className="mt-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-faint">
            Measured importance
          </p>
          <ul className="mt-2 space-y-2">
            {info.importance.slice(0, 5).map((f) => (
              <li key={f.feature}>
                <div className="flex items-center justify-between gap-3 text-[11px]">
                  <span className="truncate text-text-muted">{f.label}</span>
                  <span className="shrink-0 tabular font-semibold text-text-muted">
                    {(f.share * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-surface-3">
                  <div className="h-full rounded-full bg-accent" style={{ width: `${f.share * 100}%` }} />
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {m && (
        <div className="mt-4 rounded-xl bg-surface-2 p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-faint">
            Tested on {m.holdout_season} — a season it never trained on
          </p>
          <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2 text-[11px]">
            <div>
              <dt className="text-text-faint">Typical miss</dt>
              <dd className="tabular font-semibold text-text">
                {m.val_mae.toFixed(1)}
                <span className="ml-1 font-normal text-text-faint">
                  (vs {m.baseline_mae.toFixed(1)} for recent form alone)
                </span>
              </dd>
            </div>
            <div>
              <dt className="text-text-faint">Skill vs. the player's own average</dt>
              <dd className="tabular font-semibold text-text">
                {(m.val_r2_within * 100).toFixed(1)}%
              </dd>
            </div>
            <div className="col-span-2">
              <dt className="text-text-faint">Calibration</dt>
              <dd className="text-text-muted">
                said <span className="tabular font-semibold text-text">{(m.stated_rate * 100).toFixed(1)}%</span>,
                actually happened{' '}
                <span className="tabular font-semibold text-text">{(m.actual_rate * 100).toFixed(1)}%</span>{' '}
                <span className="text-text-faint">across {m.val_rows.toLocaleString()} games</span>
              </dd>
            </div>
          </dl>
          <p className="mt-2 text-[10px] leading-relaxed text-text-faint">
            That skill figure is deliberately the unflattering one. Scored against the
            league average this model looks like {(m.val_r2 * 100).toFixed(0)}%, but almost all
            of that is just knowing a starter out-produces a backup — no model needed. Against
            each player's <em>own</em> recent average, which is the question that actually
            matters here, it adds {(m.val_r2_within * 100).toFixed(1)}%. Single-game production
            is mostly game script and target luck, and no public model built on box scores
            changes that. Treat every number here as rough odds, not a forecast.
          </p>
        </div>
      )}

      {info.learn_more_url && (
        <a
          href={info.learn_more_url}
          target="_blank"
          rel="noreferrer"
          className="mt-4 inline-flex items-center gap-1 text-xs font-semibold text-accent-soft underline underline-offset-2"
        >
          {info.learn_more_label ?? 'Learn more'}
          <ArrowTopRightOnSquareIcon className="h-3 w-3" />
        </a>
      )}
    </div>
  )
}
