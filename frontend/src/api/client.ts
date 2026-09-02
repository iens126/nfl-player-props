import {
  ApiError,
  type ChartResponse,
  type DefenseSummary,
  type GameLogResponse,
  type PlayerListItem,
  type PlayerSummary,
  type ProjectionRequest,
  type ProjectionResponse,
  type ScheduleGame,
  type Team,
} from './types'

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch {
    throw new ApiError(0, 'Could not reach the API. Check your connection and try again.')
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
  playerChart: (name: string, stat: string, opponent: string, range: '3' | '5' | '10' | 'season') => {
    const qs = new URLSearchParams({ stat, opponent, range })
    return request<ChartResponse>(`/api/players/${encodeURIComponent(name)}/chart?${qs.toString()}`)
  },
  defense: (team: string) => request<DefenseSummary>(`/api/defense/${encodeURIComponent(team)}`),
  projection: (body: ProjectionRequest) =>
    request<ProjectionResponse>('/api/projection', { method: 'POST', body: JSON.stringify(body) }),
  scheduleUpcoming: (days = 7) => request<ScheduleGame[]>(`/api/schedule/upcoming?days=${days}`),
}

export { ApiError }
