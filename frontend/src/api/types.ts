export interface Team {
  abbr: string
  name: string
  color: string | null
}

export interface PlayerListItem {
  name: string
  team: string
  position: string
}

export interface StabilityStat {
  stat: string
  mean: number
  std: number
  cv: number
  rating: 'HIGH' | 'MEDIUM' | 'LOW' | null
}

export interface PlayerSummary {
  name: string
  team: string
  position: string
  headshot_url: string | null
  games_played: number
  available_stats: string[]
  stability: StabilityStat[]
  season_averages: Record<string, number>
  recent_averages: Record<string, number>
}

export interface GameLogRow {
  week: number
  opponent: string | null
  [stat: string]: number | string | null
}

export interface GameLogResponse {
  player: string
  columns: string[]
  rows: GameLogRow[]
}

export interface ChartWeek {
  week: number
  opponent: string | null
  player_value: number | null
  defense_allowed: number | null
}

export interface ChartResponse {
  stat: string
  defense_stat: string
  defense_team: string
  weeks: ChartWeek[]
  player_average: number | null
  defense_average: number | null
}

export interface DefenseStatRank {
  rank: number
  of: number
  value: number
}

export interface DefenseSection {
  weekly: Record<string, number | string | null>[]
  season_average: Record<string, number | null>
  recent_average: Record<string, number | null>
  league_rank: Record<string, DefenseStatRank>
  league_size: number
}

export interface DefenseSummary {
  team: string
  passing: DefenseSection
  rushing: DefenseSection
}

export interface ProjectionRequest {
  player: string
  opponent: string
  stat: string
  line: number
}

export interface ProjectionResponse extends ProjectionRequest {
  projection: number
  prob_over: number
  prob_under: number
  weight: number
  recent_average: number
  recent_games: number
  simulated_std: number
  simulations: number
  window_games: number
}

export interface ScheduleGame {
  gameday: string
  home_team: string
  away_team: string
  week: number | null
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}
