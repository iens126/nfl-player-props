import clsx from 'clsx'
import { ArrowTopRightOnSquareIcon } from '@heroicons/react/24/outline'
import type { OddsResponse, ProjectionResponse } from '../../api/types'

function formatPrice(price: number | null) {
  if (price === null || price === undefined) return '—'
  return price > 0 ? `+${price}` : `${price}`
}

/**
 * Sportsbook lines next to the model's number.
 *
 * The comparison people actually want is the model's over probability against
 * the book's *implied* probability. Implied probability includes the book's
 * margin, so the two sides of a market sum to more than 100% - that overround
 * is shown rather than hidden, because a naive "we say 55%, they say 52%"
 * reading of a vigged price overstates the edge.
 */
export function OddsComparison({
  odds,
  result,
  loading,
}: {
  odds: OddsResponse | null
  result: ProjectionResponse
  loading: boolean
}) {
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

  const modelPct = result.prob_over * 100

  return (
    <div className="rounded-2xl border border-border bg-surface p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-text-muted">Sportsbook lines</h3>
        <span className="text-xs text-text-faint">{odds.books.length} books</span>
      </div>
      <p className="mt-1 text-xs text-text-faint">
        Model says <span className="font-semibold text-text">{modelPct.toFixed(1)}%</span> over{' '}
        {result.line}. Book percentages include their margin, so both sides add to over 100%.
      </p>

      <div className="mt-4 -mx-1 overflow-x-auto scroll-thin">
        <table className="w-full min-w-[380px] border-collapse text-xs">
          <thead>
            <tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-text-faint">
              <th className="px-1 py-2 font-semibold">Book</th>
              <th className="px-1 py-2 text-right font-semibold">Line</th>
              <th className="px-1 py-2 text-right font-semibold">Over</th>
              <th className="px-1 py-2 text-right font-semibold">Implied</th>
              <th className="px-1 py-2 text-right font-semibold">vs model</th>
            </tr>
          </thead>
          <tbody>
            {odds.books.map((b) => {
              const implied = b.implied_over === null ? null : b.implied_over * 100
              // Only a like-for-like comparison when the book is pricing the
              // same number the model was asked about.
              const sameLine = b.line !== null && Math.abs(b.line - result.line) < 0.01
              const edge = implied === null || !sameLine ? null : modelPct - implied
              return (
                <tr key={b.book} className="border-b border-border/60 last:border-0">
                  <td className="px-1 py-2.5 font-semibold text-text">{b.book}</td>
                  <td className="px-1 py-2.5 text-right tabular text-text-muted">{b.line ?? '—'}</td>
                  <td className="px-1 py-2.5 text-right tabular text-text-muted">
                    {formatPrice(b.over_price)}
                  </td>
                  <td className="px-1 py-2.5 text-right tabular text-text-muted">
                    {implied === null ? '—' : `${implied.toFixed(1)}%`}
                  </td>
                  <td
                    className={clsx(
                      'px-1 py-2.5 text-right tabular font-semibold',
                      edge === null ? 'text-text-faint' : edge > 0 ? 'text-over' : 'text-under',
                    )}
                    title={sameLine ? undefined : "The book is pricing a different number, so these aren't directly comparable"}
                  >
                    {edge === null ? (sameLine ? '—' : 'diff. line') : `${edge > 0 ? '+' : ''}${edge.toFixed(1)}`}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-text-faint">
        A positive "vs model" means the model rates the over higher than the book's price implies.
        That is a disagreement, not an edge — the books price in injuries, weather and late news
        this model never sees. Informational only.
      </p>
      {odds.fetched_at && (
        <p className="mt-1.5 text-[11px] text-text-faint">
          Fetched {new Date(odds.fetched_at).toLocaleTimeString()}
          {odds.requests_remaining ? ` · ${odds.requests_remaining} API credits left` : ''}
        </p>
      )}
    </div>
  )
}
