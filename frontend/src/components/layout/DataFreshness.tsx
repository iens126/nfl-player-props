import { useEffect, useState } from 'react'
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { api } from '../../api/client'
import type { Manifest } from '../../engine/bundle'

/**
 * How old the data is.
 *
 * The app serves a bundle rebuilt on a schedule rather than querying nflverse
 * live. That means the one failure this architecture has is silent: if the
 * refresh job stops running, the CDN keeps serving the last good bundle and
 * the site looks perfectly healthy while quietly showing week-old numbers.
 * Showing the age turns that into something a person can notice.
 */

const STALE_AFTER_HOURS = 36

function describeAge(generatedAt: string): { text: string; hours: number } | null {
  const generated = new Date(generatedAt)
  if (Number.isNaN(generated.getTime())) return null

  const hours = (Date.now() - generated.getTime()) / 36e5
  if (hours < 1) return { text: 'updated in the last hour', hours }
  if (hours < 24) return { text: `updated ${Math.round(hours)}h ago`, hours }
  const days = Math.round(hours / 24)
  return { text: `updated ${days} day${days === 1 ? '' : 's'} ago`, hours }
}

export function DataFreshness({ className }: { className?: string }) {
  const [manifest, setManifest] = useState<Manifest | null>(null)

  useEffect(() => {
    let cancelled = false
    api.manifest()
      .then((m) => { if (!cancelled) setManifest(m) })
      .catch(() => { /* the footer is not worth an error state */ })
    return () => { cancelled = true }
  }, [])

  if (!manifest) return null
  const age = describeAge(manifest.generated_at)
  if (!age) return null

  const stale = age.hours > STALE_AFTER_HOURS
  const seasons = manifest.seasons.length
    ? `${manifest.seasons[0]}–${manifest.seasons[manifest.seasons.length - 1]}`
    : null

  return (
    <p
      className={clsx('flex flex-wrap items-center gap-1.5', stale && 'text-warn', className)}
      title={`Data bundle generated ${new Date(manifest.generated_at).toLocaleString()}`}
    >
      {stale && <ExclamationTriangleIcon className="h-3.5 w-3.5 shrink-0" />}
      <span>
        Stats {age.text}
        {seasons ? ` · ${seasons} seasons` : ''}
        {manifest.players ? ` · ${manifest.players} players` : ''}
        {stale && ' — the scheduled refresh may not be running'}
      </span>
    </p>
  )
}
