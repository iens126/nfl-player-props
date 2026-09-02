import type { DefenseSection, DefenseSummary } from '../../api/types'
import { statLabel } from '../../lib/statLabels'

const PASS_DISPLAY_STATS = ['passing_yards', 'passing_tds', 'yards_per_att', 'passing_interceptions']
const RUSH_DISPLAY_STATS = ['rushing_yards', 'rushing_tds', 'yards_per_car', 'carries']

export function DefenseMatchup({
  defense,
  showPassing,
  showRushing,
}: {
  defense: DefenseSummary
  showPassing: boolean
  showRushing: boolean
}) {
  if (!showPassing && !showRushing) return null

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {showPassing && (
        <DefenseSectionCard title={`${defense.team} Pass Defense`} section={defense.passing} statKeys={PASS_DISPLAY_STATS} />
      )}
      {showRushing && (
        <DefenseSectionCard title={`${defense.team} Run Defense`} section={defense.rushing} statKeys={RUSH_DISPLAY_STATS} />
      )}
    </div>
  )
}

function DefenseSectionCard({ title, section, statKeys }: { title: string; section: DefenseSection; statKeys: string[] }) {
  return (
    <div className="rounded-2xl border border-border bg-surface-2 p-4 sm:p-5">
      <h3 className="text-sm font-semibold text-text">{title}</h3>
      <p className="mt-0.5 text-xs text-text-faint">Allowed per game, league rank shown of {section.league_size} teams</p>

      <div className="mt-4 space-y-3.5">
        {statKeys.map((key) => {
          const rank = section.league_rank[key]
          const seasonAvg = section.season_average[key]
          const recentAvg = section.recent_average[key]
          if (seasonAvg === null || seasonAvg === undefined) return null
          const percentile = rank ? Math.round(((rank.of - rank.rank + 1) / rank.of) * 100) : null

          return (
            <div key={key}>
              <div className="flex items-baseline justify-between text-xs">
                <span className="font-medium text-text-muted">{statLabel(key)}</span>
                <span className="tabular text-text-faint">
                  {rank ? `Rank ${rank.rank} of ${rank.of}` : '—'}
                </span>
              </div>
              <div className="mt-1 flex items-center gap-3">
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-3">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-accent to-cyan"
                    style={{ width: `${percentile ?? 0}%` }}
                  />
                </div>
                <span className="w-16 shrink-0 text-right text-sm font-semibold tabular text-text">
                  {seasonAvg.toFixed(1)}
                </span>
              </div>
              {recentAvg !== null && recentAvg !== undefined && (
                <p className="mt-0.5 text-right text-[11px] text-text-faint tabular">last 3: {recentAvg.toFixed(1)}</p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
