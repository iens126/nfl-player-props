import { useState } from 'react'
import { ArrowTopRightOnSquareIcon } from '@heroicons/react/24/outline'
import type { AlternateLine, AlternatesResponse } from '../../api/types'
import { statLabel } from '../../lib/statLabels'
import { useTheme } from '../../lib/theme'
import { BookSwatch } from './BookSwatch'
import { OddsFreshness } from './OddsFreshness'

/**
 * Explore the whole ladder of lines a book will price, not just the main one.
 *
 * A standard prop market gives one number — the line the book expects to split
 * action on. The alternate market gives the milestone ladder around it, so the
 * same receiver can be taken at 40+ for a short price or 100+ for a long one.
 * Sliding through that ladder is the clearest way to see what you give up in
 * price for a softer number.
 *
 * Every book's price is shown as posted, with the probability it implies. No
 * book is singled out as "best" and no gap against the model is scored: the
 * point is to show what's on offer, not to pick for anyone.
 */

function formatPrice(price: number | null): string {
  if (price === null || price === undefined) return '—'
  return price > 0 ? `+${price}` : `${price}`
}

/** American odds -> the probability they imply, the book's margin included. */
function impliedProbability(price: number | null): number | null {
  if (price === null || price === undefined || price === 0) return null
  return price < 0 ? -price / (-price + 100) : 100 / (price + 100)
}

function formatPercent(value: number | null): string {
  return value === null ? '—' : `${(value * 100).toFixed(1)}%`
}

export function LineExplorer({
  alternates,
  loading,
  oddsPending,
  onProbabilityFor,
  onRequest,
  requested,
}: {
  alternates: AlternatesResponse | null
  loading: boolean
  /** True while the main odds call is still resolving the game. */
  oddsPending: boolean
  /** Model P(over) at an arbitrary line — closed-form, so this is cheap. */
  onProbabilityFor: (line: number) => number | null
  onRequest: () => void
  requested: boolean
}) {
  const { theme } = useTheme()
  const isDark = theme === 'dark'

  const lines: AlternateLine[] = alternates?.lines ?? []

  // Reset the slider when a different ladder arrives. This component stays
  // mounted across player and stat changes, so without it the slider kept the
  // previous ladder's position — landing on an unrelated rung, or clamping to
  // the end of a shorter ladder.
  //
  // Compare on the `alternates` prop, not on `lines`: the latter is
  // `alternates?.lines ?? []`, a fresh array literal on every render whenever
  // the prop is null, which makes the check always true and loops forever.
  // The prop's identity only changes when the parent actually loads a ladder.
  const [seen, setSeen] = useState<AlternatesResponse | null>(alternates)
  const [index, setIndex] = useState(0)
  if (seen !== alternates) {
    setSeen(alternates)
    setIndex(0)
  }

  const safeIndex = Math.min(index, Math.max(lines.length - 1, 0))
  const selected = lines[safeIndex]

  if (!requested) {
    return (
      <div className="rounded-2xl border border-border bg-surface p-5">
        <h3 className="text-xs font-bold uppercase tracking-wider text-text-muted">
          Alternate lines
        </h3>
        <p className="mt-2 text-xs leading-relaxed text-text-muted">
          Books price the same player at several thresholds — a softer line for a
          shorter price, a longer one for a bigger payout. Load the ladder to
          compare them.
        </p>
        <button
          type="button"
          onClick={onRequest}
          disabled={oddsPending}
          className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-semibold text-accent-soft transition-colors hover:bg-accent/15 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {oddsPending ? 'Finding the game…' : 'Load alternate lines'}
        </button>
        <p className="mt-2 text-[11px] text-text-faint">
          Uses one API credit per game and stat, so it's loaded on request rather
          than automatically.
        </p>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="rounded-2xl border border-border bg-surface p-5">
        <h3 className="text-xs font-bold uppercase tracking-wider text-text-muted">Alternate lines</h3>
        <p className="mt-3 text-xs text-text-faint">Loading the ladder…</p>
      </div>
    )
  }

  if (!alternates || alternates.status !== 'ok' || lines.length === 0) {
    return (
      <div className="rounded-2xl border border-border bg-surface p-5">
        <h3 className="text-xs font-bold uppercase tracking-wider text-text-muted">Alternate lines</h3>
        <p className="mt-2 text-xs leading-relaxed text-text-muted">
          {alternates?.message ?? 'No alternate lines available.'}
        </p>
        {alternates?.status === 'not_configured' && (
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

  const modelProbability = onProbabilityFor(selected.line)
  const singleRung = lines.length < 2

  return (
    <div className="rounded-2xl border border-border bg-surface p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-text-muted">
          Alternate lines
        </h3>
        <span className="text-xs text-text-faint">
          {lines.length} threshold{lines.length === 1 ? '' : 's'}
          {alternates.stat ? ` · ${statLabel(alternates.stat)}` : ''}
        </span>
      </div>

      <div className="mt-5 flex items-end justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-text-faint">Line</p>
          <p className="mt-0.5 text-3xl font-extrabold tabular tracking-tight text-text">
            {selected.line}
          </p>
        </div>
        <div className="text-right">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-text-faint">
            Model says over
          </p>
          <p className="mt-0.5 text-3xl font-extrabold tabular tracking-tight text-text">
            {formatPercent(modelProbability)}
          </p>
        </div>
      </div>

      {!singleRung && (
        <>
          <input
            type="range"
            min={0}
            max={lines.length - 1}
            step={1}
            value={safeIndex}
            onChange={(e) => setIndex(Number(e.target.value))}
            aria-label="Alternate line"
            className="mt-4 w-full accent-accent"
          />
          <div className="flex justify-between text-[11px] tabular text-text-faint">
            <span>{lines[0].line}</span>
            <span>{lines[lines.length - 1].line}</span>
          </div>
        </>
      )}

      <div className="mt-5 -mx-1 overflow-x-auto scroll-thin">
        <table className="w-full min-w-[320px] border-collapse text-xs">
          <thead>
            <tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-text-faint">
              <th className="px-1 py-2 font-semibold">Book</th>
              <th className="px-1 py-2 text-right font-semibold">Over</th>
              <th className="px-1 py-2 text-right font-semibold">Implied</th>
              <th className="px-1 py-2 text-right font-semibold">Under</th>
            </tr>
          </thead>
          <tbody>
            {selected.books.map((b) => (
              <tr key={b.book} className="border-b border-border/60 last:border-0">
                <td className="px-1 py-2.5">
                  <BookSwatch book={b.book} isDark={isDark} />
                </td>
                <td className="px-1 py-2.5 text-right tabular text-text">
                  {formatPrice(b.over_price)}
                </td>
                <td className="px-1 py-2.5 text-right tabular text-text-muted">
                  {formatPercent(impliedProbability(b.over_price))}
                </td>
                <td className="px-1 py-2.5 text-right tabular text-text-muted">
                  {formatPrice(b.under_price)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-text-faint">
        Implied percentages include the book's margin, which is why a market's
        two sides add to more than 100%. A difference from the model is a
        disagreement, not an edge — the books price in news the model never sees.
      </p>
      <OddsFreshness
        fetchedAt={alternates.fetched_at}
        requestsRemaining={alternates.requests_remaining}
        className="mt-1.5 text-[11px] text-text-faint"
      />
    </div>
  )
}
