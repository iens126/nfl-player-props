import { useState } from 'react'
import { InformationCircleIcon } from '@heroicons/react/24/outline'
import type { StabilityStat } from '../../api/types'
import { Badge } from '../common/Badge'
import { stabilityTone } from '../../lib/stabilityTone'
import { statLabel } from '../../lib/statLabels'

export function StabilityPanel({ stability }: { stability: StabilityStat[] }) {
  const [showInfo, setShowInfo] = useState(false)

  return (
    <div>
      <button
        onClick={() => setShowInfo((v) => !v)}
        className="mb-3 flex items-center gap-1.5 text-xs text-text-faint transition-colors hover:text-text-muted"
      >
        <InformationCircleIcon className="h-4 w-4" />
        What does stability mean?
      </button>

      {showInfo && (
        <p className="mb-4 rounded-xl border border-border bg-surface-2 p-3.5 text-xs leading-relaxed text-text-muted">
          Stability compares a stat's week-to-week swing to its average (the coefficient of
          variation, or CV = standard deviation ÷ mean) after removing statistical outlier games.
          A lower CV means the player produces that stat more consistently game to game.{' '}
          <span className="font-semibold text-over">HIGH</span> = CV under 0.35,{' '}
          <span className="font-semibold text-warn">MEDIUM</span> = 0.35–0.65,{' '}
          <span className="font-semibold text-under">LOW</span> = above 0.65.
        </p>
      )}

      <div className="space-y-2.5">
        {stability.map((s) => (
          <div
            key={s.stat}
            className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-xl border border-border bg-surface-2 px-4 py-3"
          >
            <div>
              <p className="text-sm font-semibold text-text">{statLabel(s.stat)}</p>
              <p className="mt-0.5 text-xs text-text-faint tabular">
                avg {s.mean.toFixed(1)} · σ {s.std.toFixed(1)} · CV {s.cv.toFixed(2)}
              </p>
            </div>
            <Badge tone={stabilityTone(s.rating)}>{s.rating ?? 'N/A'} STABILITY</Badge>
          </div>
        ))}
        {stability.length === 0 && <p className="text-sm text-text-faint">Not enough data to compute stability.</p>}
      </div>
    </div>
  )
}
