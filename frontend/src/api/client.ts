import {
  ApiError,
  type ChartResponse,
  type DefenseSummary,
  type GameLogResponse,
  type ModelInfo,
  type OddsResponse,
  type OddsGamesResponse,
  type OddsBoardResponse,
  type AlternatesResponse,
  type PlayerListItem,
  type PlayerSummary,
  type ProjectionRequest,
  type ProjectionResponse,
  type ScheduleGame,
  type Team,
} from './types'
import { bundle, loadPlayer } from '../engine/bundle'
import { comparisonSeries, gameLog, type ChartRange } from '../engine/chart'
import { project } from '../engine/projection'

/**
 * The app's data layer.
 *
 * Everything except live odds is computed in the browser from a static bundle
 * on the CDN — there is no analytics server any more. This module keeps the
 * shape the components already expect, so the swap from "fetch from FastAPI"
 * to "fetch JSON and do the maths locally" didn't touch a single component.
 *
 * Odds are the one thing that still needs a server, because they need a secret
 * API key: those go to a small serverless function at /api/odds*.
 */

const ODDS_BASE = (import.meta.env.VITE_ODDS_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''

const RETRY_DELAYS_MS = [1000, 3000]

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** Only used for the odds endpoints now — everything else is a static file. */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response | undefined
  for (let attempt = 0; ; attempt++) {
    try {
      res = await fetch(`${ODDS_BASE}${path}`, {
        ...init,
        headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
      })
      if (![502, 503, 504].includes(res.status) || attempt >= RETRY_DELAYS_MS.length) break
    } catch {
      if (attempt >= RETRY_DELAYS_MS.length) {
        throw new ApiError(0, 'Could not reach the odds service. Check your connection and try again.')
      }
    }
    await sleep(RETRY_DELAYS_MS[attempt])
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
      else if (Array.isArray(body?.detail)) detail = body.detail.map((d: { msg?: string }) => d.msg).join(', ')
    } catch {
      // ignore parse failure, use default message
    }
    throw new ApiError(res.status, detail)
  }

  return res.json() as Promise<T>
}

/** Full team name (as the books write it) -> nflverse abbreviation. */
async function abbreviationFor(name: string | null | undefined): Promise<string | null> {
  if (!name) return null
  const { team_abbr_by_name: map } = await bundle.reference()
  return map[name.trim()] ?? null
}

/** Wrap a bundle-loading failure in the error type the UI already renders. */
async function fromBundle<T>(load: () => Promise<T>, notFound?: string): Promise<T> {
  try {
    return await load()
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    if (notFound && /404|Could not load/.test(message)) throw new ApiError(404, notFound)
    throw new ApiError(0, 'Could not load the data files. Check your connection and try again.')
  }
}

export const api = {
  health: async () => {
    await bundle.manifest()
    return { status: 'ok' }
  },

  manifest: () => fromBundle(() => bundle.manifest()),

  teams: async (): Promise<Team[]> => (await fromBundle(() => bundle.reference())).teams,

  positions: async (): Promise<string[]> => (await fromBundle(() => bundle.reference())).positions,

  scheduleUpcoming: async (days = 7): Promise<ScheduleGame[]> => {
    const { schedule } = await fromBundle(() => bundle.reference())
    // The bundle carries a long horizon; the caller picks the window it wants.
    const cutoff = new Date()
    cutoff.setDate(cutoff.getDate() + days)
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    return schedule.filter((game) => {
      const [y, m, d] = game.gameday.split('-').map(Number)
      const date = new Date(y, m - 1, d)
      return date >= today && date <= cutoff
    })
  },

  models: async (stat?: string): Promise<ModelInfo[]> => {
    const { catalog, models } = await fromBundle(() => bundle.models())
    const list = catalog as ModelInfo[]
    if (!stat) return list
    // Attach the trained model's measured numbers for the stat on screen.
    const trained = models[stat]
    return list.map((info) => {
      if (info.key !== 'ml' || !trained) return info
      return {
        ...info,
        metrics: trained.metrics as unknown as ModelInfo['metrics'],
        importance: trained.importance,
        attends_to: trained.importance.slice(0, 4).map((f) => f.label),
      }
    })
  },

  players: async (params: { team?: string; position?: string; q?: string; limit?: number }) => {
    const { players } = await fromBundle(() => bundle.index())
    let list: PlayerListItem[] = players.map((p) => ({
      name: p.name, team: p.team, position: p.position,
    }))
    if (params.team) list = list.filter((p) => p.team === params.team!.toUpperCase())
    if (params.position) list = list.filter((p) => p.position === params.position!.toUpperCase())
    if (params.q) {
      const needle = params.q.toLowerCase()
      list = list.filter((p) => p.name.toLowerCase().includes(needle))
    }
    return list.slice(0, params.limit ?? 50)
  },

  playerSummary: async (name: string): Promise<PlayerSummary> => {
    const file = await fromBundle(() => loadPlayer(name), `No data found for player '${name}'`)
    return file.summary
  },

  /** Raw career game rows for a player — what the pick tracker settles against. */
  playerGames: async (name: string) => {
    const file = await fromBundle(() => loadPlayer(name), `No data found for player '${name}'`)
    return file.games
  },

  playerGameLog: async (name: string): Promise<GameLogResponse> => {
    const [file, aggregates] = await Promise.all([
      fromBundle(() => loadPlayer(name), `No data found for player '${name}'`),
      fromBundle(() => bundle.aggregates()),
    ])
    const stats = file.summary.available_stats
    return {
      player: name,
      columns: ['week', 'opponent', ...stats],
      rows: gameLog(file.games, stats, aggregates.constants.current_season),
    }
  },

  playerChart: async (
    name: string, stat: string, opponent: string, range: ChartRange,
  ): Promise<ChartResponse> => {
    const [file, aggregates] = await Promise.all([
      fromBundle(() => loadPlayer(name), `No data found for player '${name}'`),
      fromBundle(() => bundle.aggregates()),
    ])
    try {
      return comparisonSeries(file.games, stat, opponent.toUpperCase(), range, aggregates)
    } catch (error) {
      throw new ApiError(400, error instanceof Error ? error.message : 'Could not build the chart')
    }
  },

  defense: (team: string): Promise<DefenseSummary> =>
    fromBundle(() => bundle.defense(team.toUpperCase()), `Unknown team '${team}'`),

  projection: async (body: ProjectionRequest): Promise<ProjectionResponse> => {
    const [file, aggregates, models] = await Promise.all([
      fromBundle(() => loadPlayer(body.player), `No data found for player '${body.player}'`),
      fromBundle(() => bundle.aggregates()),
      fromBundle(() => bundle.models()),
    ])

    const playerTeam = file.summary.team
    if (body.opponent === playerTeam) {
      throw new ApiError(400, "Opponent must be different from the player's own team")
    }
    try {
      return project({
        player: body.player,
        opponent: body.opponent.toUpperCase(),
        stat: body.stat,
        line: body.line,
        model: body.model ?? 'ensemble',
        games: file.games,
        aggregates,
        models,
      })
    } catch (error) {
      throw new ApiError(400, error instanceof Error ? error.message : 'Could not calculate a projection')
    }
  },

  /**
   * The model's P(over) at each of several lines, in one pass.
   *
   * The models are closed-form, so pricing a whole ladder of thresholds costs
   * microseconds — which is what makes the line explorer's slider feel instant
   * instead of firing a request per step.
   */
  probabilitiesFor: async (
    body: Omit<ProjectionRequest, 'line'> & { lines: number[] },
  ): Promise<Record<number, number>> => {
    const [file, aggregates, models] = await Promise.all([
      fromBundle(() => loadPlayer(body.player), `No data found for player '${body.player}'`),
      fromBundle(() => bundle.aggregates()),
      fromBundle(() => bundle.models()),
    ])
    const out: Record<number, number> = {}
    for (const line of body.lines) {
      try {
        out[line] = project({
          player: body.player,
          opponent: body.opponent.toUpperCase(),
          stat: body.stat,
          line,
          model: body.model ?? 'ensemble',
          games: file.games,
          aggregates,
          models,
        }).prob_over
      } catch {
        // A line the model can't price just has no reading.
      }
    }
    return out
  },

  // --- live odds: the only thing still served by a function ---
  odds: (params: { player: string; team: string; opponent: string; stat: string }) => {
    const qs = new URLSearchParams(params)
    return request<OddsResponse>(`/api/odds?${qs.toString()}`)
  },
  oddsGames: () => request<OddsGamesResponse>('/api/odds/games'),

  /** The full line/price ladder for one player. Costs an extra API credit, so
   *  this is only called when a user explicitly opens the explorer. */
  oddsAlternates: (eventId: string, stat: string, player: string) => {
    const qs = new URLSearchParams({ event_id: eventId, stat, player })
    return request<AlternatesResponse>(`/api/odds/alternates?${qs.toString()}`)
  },

  oddsBoard: async (eventId: string, stat: string): Promise<OddsBoardResponse> => {
    const qs = new URLSearchParams({ event_id: eventId, stat })
    const board = await request<OddsBoardResponse>(`/api/odds/board?${qs.toString()}`)
    if (board.status !== 'ok') return board

    // Tag each row with the player's team and their opponent in this game, so
    // clicking through carries the matchup rather than re-guessing it. This
    // used to happen server-side against the roster; the static index carries
    // the same information, which keeps the odds function free of pandas.
    try {
      const { players } = await bundle.index()
      const teamByPlayer = new Map(players.map((p) => [p.name, p.team]))
      const [home, away] = await Promise.all([
        abbreviationFor(board.game?.home_team),
        abbreviationFor(board.game?.away_team),
      ])
      if (!home || !away) return board

      const other: Record<string, string> = { [home]: away, [away]: home }
      board.entries = board.entries.map((entry) => {
        const team = teamByPlayer.get(entry.player)
        // A player whose team isn't in this game (a name collision, or a
        // mid-week move) is left untagged rather than guessed at.
        return team && other[team]
          ? { ...entry, team, opponent: other[team] }
          : { ...entry, team: null, opponent: null }
      })
    } catch {
      // Tagging is a convenience; the board is still useful without it.
    }
    return board
  },
}

export { ApiError }
