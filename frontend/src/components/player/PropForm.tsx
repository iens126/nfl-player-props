import { statLabel } from '../../lib/statLabels'

export function PropForm({
  availableStats,
  stat,
  onStatChange,
  line,
  onLineChange,
}: {
  availableStats: string[]
  stat: string | null
  onStatChange: (stat: string) => void
  line: string
  onLineChange: (line: string) => void
}) {
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
    </div>
  )
}
