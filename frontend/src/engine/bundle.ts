/**
 * Loader for the static data bundle.
 *
 * Everything the app used to ask a server for now lives as JSON on the CDN.
 * Files are fetched once and memoised for the page's lifetime: the shared
 * artifacts (aggregates, models, reference) are a fixed ~110 KB gzipped, and
 * each player is about 1 KB on top, so a session costs a fraction of one
 * cold-start round trip to the old backend.
 */

import type {
  DefenseSummary, PlayerListItem, PlayerSummary, ScheduleGame, Team,
} from '../api/types'

const BASE = `${import.meta.env.BASE_URL ?? '/'}data`.replace(/\/{2,}/g, '/')

export interface GameRow {
  season: number
  week: number
  team: string | null
  opponent_team: string | null
  position: string | null
  [stat: string]: number | string | null
}

export interface PlayerFile {
  summary: PlayerSummary
  games: GameRow[]
}

export interface IndexEntry {
  name: string
  slug: string
  team: string
  position: string
}

export interface Manifest {
  version: number
  generated_at: string
  seasons: number[]
  players: number
  teams: number
  model_metrics: Record<string, Record<string, number>>
}

export interface Constants {
  stat_map: Record<string, [string, string]>
  position_k: Record<string, number>
  default_k: number
  half_life_games: number
  max_window: number
  bettable_columns: string[]
  current_season: number
  usage_columns: Record<string, string[]>
}

export interface Aggregates {
  league_team_stats: Record<string, { mean: number; std: number }>
  defense_weekly: Record<string, { pass: Record<string, number>[]; run: Record<string, number>[] }>
  /** "TEAM|POSITION|STAT" (and "NFL|...") -> mean allowed. */
  position_allowed: Record<string, number>
  /** "POSITION|STAT" -> how much of a defense's deviation actually repeats. */
  signal_reliability: Record<string, number>
  career_defense_allowed: Record<string, Record<string, Record<string, number>>>
  constants: Constants
}

export interface TrainedModelFile {
  features: string[]
  weights: number[]
  mean: number[]
  scale: number[]
  bin_edges: number[]
  residual_percentiles: number[][]
  metrics: Record<string, number>
  importance: { feature: string; label: string; share: number }[]
}

export interface ModelsFile {
  models: Record<string, TrainedModelFile>
  catalog: unknown[]
}

export interface Reference {
  teams: Team[]
  positions: string[]
  schedule: ScheduleGame[]
  /** Full team name -> nflverse abbreviation, as the odds provider names them. */
  team_abbr_by_name: Record<string, string>
}

/** Data files are immutable per deploy, so one in-flight fetch each is enough. */
const inflight = new Map<string, Promise<unknown>>()

function load<T>(path: string): Promise<T> {
  const existing = inflight.get(path)
  if (existing) return existing as Promise<T>

  const promise = fetch(`${BASE}/${path}`).then((response) => {
    if (!response.ok) {
      inflight.delete(path) // let a later attempt retry rather than caching the failure
      throw new Error(`Could not load ${path} (${response.status})`)
    }
    return response.json()
  }).catch((error) => {
    inflight.delete(path)
    throw error
  })

  inflight.set(path, promise)
  return promise as Promise<T>
}

export const bundle = {
  manifest: () => load<Manifest>('manifest.json'),
  reference: () => load<Reference>('reference.json'),
  index: () => load<{ players: IndexEntry[] }>('index.json'),
  aggregates: () => load<Aggregates>('aggregates.json'),
  models: () => load<ModelsFile>('models.json'),
  defense: (team: string) => load<DefenseSummary>(`defense/${encodeURIComponent(team)}.json`),
  player: (slug: string) => load<PlayerFile>(`players/${encodeURIComponent(slug)}.json`),
}

/** Mirrors the slug() in scripts/precompute.py — the two must agree. */
export function slugify(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '')
}

let indexByName: Map<string, IndexEntry> | null = null

/** Look a player up by display name, loading the index on first use. */
export async function findPlayerEntry(name: string): Promise<IndexEntry | null> {
  if (!indexByName) {
    const { players } = await bundle.index()
    indexByName = new Map(players.map((p) => [p.name, p]))
  }
  return indexByName.get(name) ?? null
}

export async function loadPlayer(name: string): Promise<PlayerFile> {
  const entry = await findPlayerEntry(name)
  return bundle.player(entry?.slug ?? slugify(name))
}

export type { PlayerListItem }
