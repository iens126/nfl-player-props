import type { Tone } from '../components/common/Badge'

/**
 * Badge tone for a stability rating.
 *
 * Lives outside Badge.tsx because a module that exports both components and
 * plain functions loses fast refresh - edits to it force a full reload rather
 * than a hot swap.
 */
export function stabilityTone(rating: string | null | undefined): Tone {
  if (rating === 'HIGH') return 'high'
  if (rating === 'MEDIUM') return 'medium'
  if (rating === 'LOW') return 'low'
  return 'neutral'
}
