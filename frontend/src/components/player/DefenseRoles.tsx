import clsx from 'clsx'
import type { DefenseRoleRow } from '../../api/types'

/**
 * What a defense has allowed to each opposing role this season.
 *
 * Presented strictly as a record of what happened, for the same reason the hit
 * rate panel is: it's a count, not a forecast. Role-specific defensive
 * performance was measured and does not carry from one half of a season to the
 * next (split-half r of +0.05 for yards per target against a team's WR1, on
 * ~122 targets per defense), so a defense that has been generous to primary
 * receivers so far tells you very little about the next game. The footnote says
 * so, and every row carries its sample size so a thin one is visible as thin.
 */

const ROLE_BLURB: Record<string, string> = {
  WR: "the opponent's most-targeted receiver",
  TE: "the opponent's most-targeted tight end",
  RB: "the opponent's most-targeted back",
}

function Delta({ value, league }: { value: number | null; league: number | null }) {
  if (value === null || league === null) return <span className="text-text-faint">—</span>
  const diff = value - league
  // Above the league average means this defense gave up more than most.
  const tone = Math.abs(diff) < 2 ? 'text-text-muted' : diff > 0 ? 'text-under' : 'text-over'
  return (
    <span className={clsx('tabular', tone)}>
      {diff > 0 ? '+' : ''}{diff.toFixed(1)}
    </span>
  )
}

export function DefenseRoles({ team, roles }: { team: string; roles: DefenseRoleRow[] }) {
  if (!roles || roles.length === 0) return null

  // Lead with the primary role for each position; deeper roles are thinner and
  // less interesting, so they follow.
  const ordered = [...roles].sort(
    (a, b) => a.role - b.role || a.position.localeCompare(b.position),
  )

  return (
    <div className="mt-6 border-t border-border pt-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-text-muted">
          Allowed by opposing role
        </h3>
        <span className="text-[11px] text-text-faint">this season, from play-by-play</span>
      </div>

      <div className="mt-3 -mx-1 overflow-x-auto scroll-thin">
        <table className="w-full min-w-[520px] border-collapse text-xs">
          <thead>
            <tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-text-faint">
              <th className="px-1 py-2 font-semibold">Role</th>
              <th className="px-1 py-2 text-right font-semibold">Yds/game</th>
              <th className="px-1 py-2 text-right font-semibold">vs league</th>
              <th className="px-1 py-2 text-right font-semibold">Yds/target</th>
              <th className="px-1 py-2 text-right font-semibold">Comp%</th>
              <th className="px-1 py-2 text-right font-semibold">Rank</th>
              <th className="px-1 py-2 text-right font-semibold">Sample</th>
            </tr>
          </thead>
          <tbody>
            {ordered.map((row) => {
              const thin = row.games < 6
              return (
                <tr key={row.label} className="border-b border-border/60 last:border-0">
                  <td className="px-1 py-2 font-semibold text-text" title={ROLE_BLURB[row.position]}>
                    {row.label}
                  </td>
                  <td className="px-1 py-2 text-right tabular font-semibold text-text">
                    {row.yards_per_game?.toFixed(1) ?? '—'}
                  </td>
                  <td className="px-1 py-2 text-right">
                    <Delta value={row.yards_per_game} league={row.league_yards_per_game} />
                  </td>
                  <td className="px-1 py-2 text-right tabular text-text-muted">
                    {row.yards_per_target?.toFixed(1) ?? '—'}
                  </td>
                  <td className="px-1 py-2 text-right tabular text-text-muted">
                    {row.completion_rate === null ? '—' : `${(row.completion_rate * 100).toFixed(0)}%`}
                  </td>
                  <td className="px-1 py-2 text-right tabular text-text-muted">
                    {row.rank ? `${row.rank}/${row.of}` : '—'}
                  </td>
                  <td
                    className={clsx('px-1 py-2 text-right tabular', thin ? 'text-warn' : 'text-text-faint')}
                    title={thin ? 'Few games — read this row with caution' : undefined}
                  >
                    {row.games}g · {row.targets}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-text-faint">
        Roles come from usage — {team}'s opponents ranked within their own team and position by
        targets. <span className="font-semibold text-text-muted">This is a record, not a
        forecast.</span> Measured across three seasons, how a defense fares against a particular
        role barely carries from one half of a season to the next, so a number here explains what
        already happened rather than predicting the next game. A defense's overall pass defense,
        above, is the part that does persist.
      </p>
    </div>
  )
}
