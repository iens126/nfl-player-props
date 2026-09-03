import { useEffect, useState } from 'react'
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'

/**
 * How old the displayed sportsbook lines are.
 *
 * Odds are the one thing here that moves by the minute — a line can shift on an
 * inactive-list report between one page load and the next — so "when was this
 * fetched" is not a footnote, it's part of reading the number honestly. It also
 * isn't necessarily live even when freshly loaded: responses are cached server
 * side for ODDS_CACHE_MINUTES (10 by default) to conserve API credits.
 *
 * A bare clock time couldn't carry that: it showed no date, so yesterday's
 * fetch read as current, and it never updated, so it silently aged on screen.
 * This shows elapsed time, keeps counting while the page is open, and says
 * plainly when the data is old enough to distrust.
 */

// The server cache is 10 minutes, so anything past ~20 means the page has been
// sitting open rather than the cache simply not having turned over.
const STALE_AFTER_MINUTES = 20

function describe(minutes: number): string {
  if (minutes < 1) return 'moments ago'
  if (minutes < 60) return `${Math.floor(minutes)} min ago`
  const hours = minutes / 60
  if (hours < 24) return `${Math.floor(hours)}h ago`
  const days = Math.floor(hours / 24)
  return `${days} day${days === 1 ? '' : 's'} ago`
}

export function OddsFreshness({
  fetchedAt,
  requestsRemaining,
  className,
}: {
  fetchedAt: string | null
  requestsRemaining?: string | null
  className?: string
}) {
  // Re-render on a timer so the age stays true while the page is open.
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const handle = setInterval(() => setNow(Date.now()), 30_000)
    return () => clearInterval(handle)
  }, [])

  if (!fetchedAt) return null
  const fetched = new Date(fetchedAt)
  if (Number.isNaN(fetched.getTime())) return null

  const minutes = (now - fetched.getTime()) / 60_000
  const stale = minutes > STALE_AFTER_MINUTES

  return (
    <span
      className={clsx('inline-flex flex-wrap items-center gap-1', stale && 'text-warn', className)}
      title={`Lines fetched ${fetched.toLocaleString()}. Cached briefly to conserve API credits, so they may lag the books slightly.`}
    >
      {stale && <ExclamationTriangleIcon className="h-3 w-3 shrink-0" />}
      <span>
        Lines fetched {describe(minutes)}
        {stale && ' — reload for current prices'}
        {requestsRemaining ? ` · ${requestsRemaining} API credits left` : ''}
      </span>
    </span>
  )
}
