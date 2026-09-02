import { statLabel } from '../../lib/statLabels'
import type { ModelInfo, ModelKey } from '../../api/types'

export function PropForm({
  availableStats,
  stat,
  onStatChange,
  line,
  onLineChange,
  models,
  model,
  onModelChange,
}: {
  availableStats: string[]
  stat: string | null
  onStatChange: (stat: string) => void
  line: string
  onLineChange: (line: string) => void
  models: ModelInfo[]
  model: ModelKey
  onModelChange: (model: ModelKey) => void
}) {
  const activeModel = models.find((m) => m.key === model)

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <div>
        <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-text-faint">
          Prop / Stat Category
        </label>
        <select
          className="w-full rounded-xl border border-border bg-surface-2 px-3.5 py-2.5 text-sm text-text outline-none focus:border-accent"
          value={stat ?? ''}
          onChange={(e) => onStatChange(e.target.value)}
        >
          <option value="" disabled>
            Select a stat…
          </option>
          {availableStats.map((s) => (
            <option key={s} value={s}>
              {statLabel(s)}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-text-faint">
          Prop Line
        </label>
        <input
          type="number"
          inputMode="decimal"
          step="0.5"
          min="0"
          placeholder="e.g. 247.5"
          className="w-full rounded-xl border border-border bg-surface-2 px-3.5 py-2.5 text-sm text-text tabular placeholder:text-text-faint outline-none focus:border-accent"
          value={line}
          onChange={(e) => onLineChange(e.target.value)}
        />
      </div>

      {models.length > 0 && (
        <div className="sm:col-span-2">
          <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-text-faint">
            Projection Model
          </label>
          <select
            className="w-full rounded-xl border border-border bg-surface-2 px-3.5 py-2.5 text-sm text-text outline-none focus:border-accent"
            value={model}
            onChange={(e) => onModelChange(e.target.value as ModelKey)}
          >
            {models.map((m) => (
              <option key={m.key} value={m.key}>
                {m.description}
              </option>
            ))}
          </select>
          {activeModel && (
            <p className="mt-1.5 text-xs text-text-faint">
              Every model is scored on your line regardless — this only picks which one drives the
              headline number.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
