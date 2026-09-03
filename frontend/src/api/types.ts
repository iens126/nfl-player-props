export interface Team {
  abbr: string
  name: string
  color: string | null
  color2: string | null
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
  season: number | null
  label: string | null
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

export type ModelKey = 'ml' | 'ensemble' | 'lognormal' | 'negbin' | 'empirical' | 'triangular'

export interface FeatureImportance {
  feature: string
  label: string
  share: number
}

export interface ModelMetrics {
  val_mae: number
  /** R² against the league-wide mean. Mostly reflects telling starters from
   *  backups, so it reads far higher than the model's real predictive skill. */
  val_r2: number
  /** R² against each player's own recent average — the honest measure. */
  val_r2_within: number
  baseline_mae: number
  brier: number
  stated_rate: number
  actual_rate: number
  val_rows: number
  holdout_season: number
}

export interface ModelInfo {
  key: ModelKey
  description: string
  summary: string | null
  attends_to: string[]
  learn_more_url: string | null
  learn_more_label: string | null
  trained: boolean
  metrics: ModelMetrics | null
  importance: FeatureImportance[]
}

export type HitRateWindow = 'last_3' | 'last_5' | 'last_10' | 'season' | 'career'

export interface HitRate {
  window: HitRateWindow
  games: number
  hits: number
  rate: number
  average: number
}

export interface BookLine {
  book: string
  line: number | null
  over_price: number | null
  under_price: number | null
  implied_over: number | null
  implied_under: number | null
  last_update: string | null
}

export type OddsStatus = 'ok' | 'not_configured' | 'no_market' | 'no_event' | 'error'

export interface OddsResponse {
  status: OddsStatus
  message: string | null
  books: BookLine[]
  consensus_line: number | null
  market: string | null
  fetched_at: string | null
  requests_remaining: string | null
}

export interface OddsGame {
  id: string
  home_team: string | null
  away_team: string | null
  commence_time: string | null
}

export interface OddsGamesResponse {
  status: OddsStatus
  message: string | null
  games: OddsGame[]
}

export interface OddsBoardEntry {
  player: string
  consensus_line: number | null
  books: BookLine[]
  /** Resolved from the roster; null when the book's spelling doesn't match. */
  team: string | null
  opponent: string | null
}

export interface OddsBoardResponse {
  status: OddsStatus
  message: string | null
  entries: OddsBoardEntry[]
  game: OddsGame | null
  market: string | null
  stat: string | null
  fetched_at: string | null
  requests_remaining: string | null
}

export interface ProjectionRequest {
  player: string
  opponent: string
  stat: string
  line: number
  model?: ModelKey
}

export interface ProjectionResponse {
  player: string
  opponent: string
  stat: string
  line: number
  projection: number
  prob_over: number
  prob_under: number
  weight: number
  model: string
  model_label: string
  form_average: number
  season_average: number
  recent_games: number
  effective_games: number
  std_dev: number
  window_games: number
  /** Every model's over probability for this line, keyed by model name. */
  alternatives: Record<string, number>
  /** How often the player actually reached this line, by lookback window. */
  hit_rates: HitRate[]
  ml_projection: number | null
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
