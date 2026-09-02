export const STAT_LABELS: Record<string, string> = {
  passing_yards: 'Passing Yards',
  passing_tds: 'Passing TDs',
  completions: 'Completions',
  attempts: 'Pass Attempts',
  passing_interceptions: 'Interceptions',
  targets: 'Targets',
  receptions: 'Receptions',
  receiving_yards: 'Receiving Yards',
  receiving_tds: 'Receiving TDs',
  carries: 'Carries',
  rushing_yards: 'Rushing Yards',
  rushing_tds: 'Rushing TDs',
}

export function statLabel(key: string): string {
  return STAT_LABELS[key] ?? key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

// Short header labels for dense tables.
export const STAT_SHORT: Record<string, string> = {
  passing_yards: 'PASS YD',
  passing_tds: 'PASS TD',
  completions: 'COMP',
  attempts: 'ATT',
  passing_interceptions: 'INT',
  targets: 'TGT',
  receptions: 'REC',
  receiving_yards: 'REC YD',
  receiving_tds: 'REC TD',
  carries: 'CAR',
  rushing_yards: 'RUSH YD',
  rushing_tds: 'RUSH TD',
}

export function statShort(key: string): string {
  return STAT_SHORT[key] ?? key.slice(0, 7).toUpperCase()
}

export function formatStatValue(key: string, value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  if (key.includes('yards')) return value.toFixed(0)
  if (key.includes('tds') || key === 'completions' || key === 'attempts' || key === 'receptions' || key === 'targets' || key === 'carries' || key === 'passing_interceptions') {
    return value.toFixed(1).replace(/\.0$/, '')
  }
  return value.toFixed(1)
}
