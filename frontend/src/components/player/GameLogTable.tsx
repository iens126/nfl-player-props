import clsx from 'clsx'
import type { GameLogResponse } from '../../api/types'
import { statShort } from '../../lib/statLabels'

export function GameLogTable({
  gameLog,
  highlightStat,
  line,
}: {
  gameLog: GameLogResponse
  highlightStat: string | null
  line: number | null
}) {
  const statCols = gameLog.columns.filter((c) => c !== 'week' && c !== 'opponent')

  return (
    <div className="scroll-thin overflow-x-auto rounded-2xl border border-border">
      <table className="w-full min-w-[520px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-border bg-surface-2 text-left text-[11px] font-semibold uppercase tracking-wider text-text-faint">
            <th className="px-3.5 py-3">Wk</th>
            <th className="px-3.5 py-3">Opp</th>
            {statCols.map((c) => (
              <th key={c} className="px-3.5 py-3 text-right tabular">
                {statShort(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {gameLog.rows.map((row) => {
            const value = highlightStat ? row[highlightStat] : null
            const hit = line !== null && typeof value === 'number' ? value >= line : null

            return (
              <tr
                key={row.week}
                className={clsx(
                  'border-b border-border-soft last:border-0',
                  hit === true && 'bg-over/[0.06]',
                  hit === false && 'bg-under/[0.06]',
                )}
              >
                <td className="px-3.5 py-2.5 font-semibold text-text">{row.week}</td>
                <td className="px-3.5 py-2.5 text-text-muted">{row.opponent ?? '—'}</td>
                {statCols.map((c) => {
                  const v = row[c]
                  const isHighlighted = highlightStat === c && hit !== null
                  return (
                    <td
                      key={c}
                      className={clsx(
                        'px-3.5 py-2.5 text-right tabular',
                        isHighlighted ? (hit ? 'font-bold text-over' : 'font-bold text-under') : 'text-text-muted',
                      )}
                    >
                      {typeof v === 'number' ? v : '—'}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
