import { ArrowTopRightOnSquareIcon } from '@heroicons/react/24/outline'
import type { OddsResponse } from '../../api/types'
import { OddsFreshness } from './OddsFreshness'

function formatPrice(price: number | null) {
  if (price === null || price === undefined) return '—'
  return price > 0 ? `+${price}` : `${price}`
}

/**
 * The books' current lines for this player and stat.
 *
 * Purely a listing. It deliberately does not compare these prices to the
 * model, score them, or mark any of them as value - the projection is right
 * there on the same page, and what to make of the two sitting side by side is
 * the reader's call.
 */
export function OddsList({ odds, loading }: { odds: OddsResponse | null; loading: boolean }) {
  if (loading) {
    return (
      <div className="rounded-2xl border border-border bg-surface p-5">
        <h3 className="text-xs font-bold uppercase tracking-wider text-text-muted">Sportsbook lines</h3>
        <p className="mt-3 text-xs text-text-faint">Checking the books…</p>
      </div>
    )
  }

  if (!odds) return null

  if (odds.status !== 'ok' || odds.books.length === 0) {
    return (
      <div className="rounded-2xl border border-border bg-surface p-5">
        <h3 className="text-xs font-bold uppercase tracking-wider text-text-muted">Sportsbook lines</h3>
        <p className="mt-2 text-xs leading-relaxed text-text-muted">{odds.message}</p>
        {odds.status === 'not_configured' && (
          <a
            href="https://the-odds-api.com/"
            target="_blank"
            rel="noreferrer"
            className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-accent-soft underline underline-offset-2"
          >
            Get a free API key
            <ArrowTopRightOnSquareIcon className="h-3 w-3" />
          </a>
        )}
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-border bg-surface p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-text-muted">Sportsbook lines</h3>
        {odds.consensus_line !== null && (
          <span className="text-xs text-text-faint">
            median <span className="tabular font-semibold text-text">{odds.consensus_line}</span>
          </span>
        )}
      </div>

      <div className="mt-4 -mx-1 overflow-x-auto scroll-thin">
        <table className="w-full min-w-[300px] border-collapse text-xs">
          <thead>
            <tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-text-faint">
              <th className="px-1 py-2 font-semibold">Book</th>
              <th className="px-1 py-2 text-right font-semibold">Line</th>
              <th className="px-1 py-2 text-right font-semibold">Over</th>
              <th className="px-1 py-2 text-right font-semibold">Under</th>
            </tr>
          </thead>
          <tbody>
            {odds.books.map((b) => (
              <tr key={b.book} className="border-b border-border/60 last:border-0">
                <td className="px-1 py-2.5 font-semibold text-text">{b.book}</td>
                <td className="px-1 py-2.5 text-right tabular text-text">{b.line ?? '—'}</td>
                <td className="px-1 py-2.5 text-right tabular text-text-muted">{formatPrice(b.over_price)}</td>
                <td className="px-1 py-2.5 text-right tabular text-text-muted">{formatPrice(b.under_price)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-text-faint">
        Listed for reference only. Books price in injuries, weather and late news the model never
        sees, so a difference between these numbers and the projection is not an edge — it is
        usually information the model is missing.
      </p>
      <OddsFreshness
        fetchedAt={odds.fetched_at}
        requestsRemaining={odds.requests_remaining}
        className="mt-1.5 text-[11px] text-text-faint"
      />
    </div>
  )
}
