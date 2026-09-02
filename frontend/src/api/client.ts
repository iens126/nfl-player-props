import {
  ApiError,
  type ChartResponse,
  type DefenseSummary,
  type GameLogResponse,
  type ModelInfo,
  type OddsResponse,
  type PlayerListItem,
  type PlayerSummary,
  type ProjectionRequest,
  type ProjectionResponse,
  type ScheduleGame,
  type Team,
} from './types'

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''

// The backend runs on Render's free tier, which spins the service down after
// idle periods. The first request after a spin-down wakes it back up, but
// while it's booting the request can fail outright (connection reset, or a
// 502/503 from Render's proxy) instead of just being slow. Retry a few times
// with backoff before giving up, so a cold start recovers on its own instead
// of surfacing a raw connection error to the user.
const RETRY_DELAYS_MS = [1000, 3000, 8000]

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response | undefined
  for (let attempt = 0; ; attempt++) {
    try {
      res = await fetch(`${BASE_URL}${path}`, {
        ...init,
        headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
      })
      if (![502, 503, 504].includes(res.status) || attempt >= RETRY_DELAYS_MS.length) break
    } catch {
      if (attempt >= RETRY_DELAYS_MS.length) {
        throw new ApiError(0, 'Could not reach the API. Check your connection and try again.')
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

export const api = {
  health: () => request<{ status: string }>('/health'),
  teams: () => request<Team[]>('/api/teams'),
  positions: () => request<string[]>('/api/positions'),
  models: (stat?: string) =>
    request<ModelInfo[]>(`/api/models${stat ? `?stat=${encodeURIComponent(stat)}` : ''}`),
  odds: (params: { player: string; team: string; opponent: string; stat: string }) => {
    const qs = new URLSearchParams(params)
    return request<OddsResponse>(`/api/odds?${qs.toString()}`)
  },
  players: (params: { team?: string; position?: string; q?: string; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params.team) qs.set('team', params.team)
    if (params.position) qs.set('position', params.position)
    if (params.q) qs.set('q', params.q)
    if (params.limit) qs.set('limit', String(params.limit))
    return request<PlayerListItem[]>(`/api/players?${qs.toString()}`)
  },
  playerSummary: (name: string) => request<PlayerSummary>(`/api/players/${encodeURIComponent(name)}`),
  playerGameLog: (name: string) => request<GameLogResponse>(`/api/players/${encodeURIComponent(name)}/gamelog`),
  playerChart: (name: string, stat: string, opponent: string, range: '3' | '5' | '10' | 'season' | 'career') => {
    const qs = new URLSearchParams({ stat, opponent, range })
    return request<ChartResponse>(`/api/players/${encodeURIComponent(name)}/chart?${qs.toString()}`)
  },
  defense: (team: string) => request<DefenseSummary>(`/api/defense/${encodeURIComponent(team)}`),
  projection: (body: ProjectionRequest) =>
    request<ProjectionResponse>('/api/projection', { method: 'POST', body: JSON.stringify(body) }),
  scheduleUpcoming: (days = 7) => request<ScheduleGame[]>(`/api/schedule/upcoming?days=${days}`),
}

export { ApiError }
