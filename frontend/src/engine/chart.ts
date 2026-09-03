/**
 * Performance-chart series, ported from core/stat_visualization.py.
 *
 * Two shapes, matching the Python:
 *  - week ranges align the player's games to what the defense allowed in the
 *    same week of the current season;
 *  - the career range spans multiple seasons, where weeks repeat and a single
 *    past game can't be aligned to one week of this defense, so the comparison
 *    bar drops to what that defense allowed the player's position across that
 *    whole season.
 */

import type { ChartResponse, ChartWeek, GameLogRow } from '../api/types'
import type { Aggregates, GameRow } from './bundle'

export type ChartRange = '3' | '5' | '10' | 'season' | 'career'

function numeric(value: unknown): number | null {
  return typeof value === 'number' && !Number.isNaN(value) ? value : null
}

function average(values: number[]): number | null {
  if (values.length === 0) return null
  return values.reduce((a, b) => a + b, 0) / values.length
}

/** The player's games against what `defense` allowed, week by week. */
export function comparisonSeries(
  games: GameRow[], stat: string, defense: string, range: ChartRange, aggregates: Aggregates,
): ChartResponse {
  const { constants } = aggregates
  const mapping = constants.stat_map[stat]
  if (!mapping) throw new Error(`Unsupported stat category '${stat}'`)
  const [defenseStat, defenseType] = mapping

  if (range === 'career') return careerSeries(games, stat, defense, aggregates)

  const seasonGames = games
    .filter((g) => g.season === constants.current_season)
    .sort((a, b) => Number(a.week) - Number(b.week))
  const scoped = range === 'season' ? seasonGames : seasonGames.slice(-Number(range))

  const defenseRows = aggregates.defense_weekly[defense]?.[defenseType === 'pass' ? 'pass' : 'run'] ?? []
  const allowedByWeek = new Map<number, number>()
  for (const row of defenseRows) {
    const value = numeric(row[defenseStat])
    if (value !== null) allowedByWeek.set(Number(row.week), value)
  }

  const weeks: ChartWeek[] = scoped.map((g) => ({
    week: Number(g.week),
    // Week ranges sit inside one season, so the chart labels by week alone.
    season: null,
    label: null,
    opponent: (g.opponent_team as string | null) ?? null,
    player_value: numeric(g[stat]),
    defense_allowed: allowedByWeek.get(Number(g.week)) ?? null,
  }))

  return {
    stat,
    defense_stat: defenseStat,
    defense_team: defense,
    weeks,
    player_average: average(weeks.map((w) => w.player_value).filter((v): v is number => v !== null)),
    defense_average: average(
      weeks.map((w) => w.defense_allowed).filter((v): v is number => v !== null),
    ),
  }
}

/** Whole career, with the defense reference at season resolution. */
function careerSeries(
  games: GameRow[], stat: string, defense: string, aggregates: Aggregates,
): ChartResponse {
  const mapping = aggregates.constants.stat_map[stat]
  const [defenseStat] = mapping

  const ordered = [...games].sort(
    (a, b) => Number(a.season) - Number(b.season) || Number(a.week) - Number(b.week),
  )
  const position = String(ordered[ordered.length - 1]?.position ?? '')
  const bySeason = aggregates.career_defense_allowed[`${defense}|${position}`] ?? {}

  const weeks: ChartWeek[] = ordered.map((g) => {
    const season = Number(g.season)
    const allowed = bySeason[String(season)]?.[stat]
    return {
      week: Number(g.week),
      season,
      label: `'${String(season).slice(2)} W${Number(g.week)}`,
      opponent: (g.opponent_team as string | null) ?? null,
      player_value: numeric(g[stat]),
      defense_allowed: typeof allowed === 'number' ? allowed : null,
    }
  })

  const allowedValues = Object.values(bySeason)
    .map((s) => s[stat])
    .filter((v): v is number => typeof v === 'number')

  return {
    stat,
    defense_stat: defenseStat,
    defense_team: defense,
    weeks,
    player_average: average(weeks.map((w) => w.player_value).filter((v): v is number => v !== null)),
    defense_average: average(allowedValues),
  }
}

/** Game-log table rows, matching the shape the old API returned. */
export function gameLog(games: GameRow[], stat: string[], currentSeason: number): GameLogRow[] {
  const rows = [...games]
    .filter((g) => g.season === currentSeason)
    .sort((a, b) => Number(b.week) - Number(a.week))
    .map((g) => {
      const record: GameLogRow = {
        week: Number(g.week),
        opponent: (g.opponent_team as string | null) ?? null,
      }
      for (const s of stat) record[s] = numeric(g[s])
      return record
    })
  return rows
}
