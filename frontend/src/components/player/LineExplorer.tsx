import { useMemo, useState } from 'react'
import clsx from 'clsx'
import { ArrowTopRightOnSquareIcon } from '@heroicons/react/24/outline'
import type { AlternateLine, AlternatesResponse } from '../../api/types'
import { bookStyle } from '../../lib/bookStyle'
import { statLabel } from '../../lib/statLabels'
import { useTheme } from '../../lib/theme'
import { BookSwatch } from './BookSwatch'

/**
 * Explore the whole ladder of lines a book will price, not just the main one.
 *
 * A standard prop market gives one number — the line the book expects to split
 * action on. The alternate market gives the milestone ladder around it, so the
 * same receiver can be taken at 40+ for a short price or 100+ for a long one.
 * Sliding through that ladder is the clearest way to see what you give up in
 * price for a softer number.
 *
 * The model's probability for the selected line is shown alongside, because it
 * costs nothing to compute in the browser. It is presented as a second opinion,
 * not as an edge: no gap is scored, ranked or flagged.
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

export function LineExplorer({
  alternates,
  loading,
  onProbabilityFor,
  onRequest,
  requested,
}: {
  alternates: AlternatesResponse | null
  loading: boolean
  /** Model P(over) at an arbitrary line — closed-form, so this is cheap. */
  onProbabilityFor: (line: number) => number | null
  onRequest: () => void
  requested: boolean
}) {
  const { theme } = useTheme()
  const isDark = theme === 'dark'
  const [index, setIndex] = useState(0)

  const lines: AlternateLine[] = useMemo(
    () => alternates?.lines ?? [],
    [alternates],
  )

  // Keep the slider in range when a new ladder arrives.
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
          className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-semibold text-accent-soft transition-colors hover:bg-accent/15"
        >
          Load alternate lines
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

  const modelProbability = selected ? onProbabilityFor(selected.line) : null
  const bookImplied = impliedProbability(selected?.best_over ?? null)

  return (
    <div className="rounded-2xl border border-border bg-surface p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-text-muted">
          Alternate lines
        </h3>
        <span className="text-xs text-text-faint">
          {lines.length} thresholds · {alternates.stat ? statLabel(alternates.stat) : ''}
        </span>
      </div>

      {/* The ladder itself */}
      <div className="mt-5">
        <div className="flex items-end justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-text-faint">
              Line
            </p>
            <p className="mt-0.5 text-3xl font-extrabold tabular tracking-tight text-text">
              {selected.line}
            </p>
          </div>
          <div className="text-right">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-text-faint">
              Best over price
            </p>
            <p className="mt-0.5 text-3xl font-extrabold tabular tracking-tight text-text">
              {formatPrice(selected.best_over)}
            </p>
          </div>
        </div>

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
      </div>

      {/* What the two readings say at this threshold */}
      <div className="mt-5 grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-border bg-surface-2 p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-faint">
            Book implied
          </p>
          <p className="mt-1 text-xl font-bold tabular text-text">
            {bookImplied === null ? '—' : `${(bookImplied * 100).toFixed(1)}%`}
          </p>
          <p className="mt-0.5 text-[10px] leading-tight text-text-faint">includes their margin</p>
        </div>
        <div className="rounded-xl border border-border bg-surface-2 p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-faint">
            Model says
          </p>
          <p className="mt-1 text-xl font-bold tabular text-text">
            {modelProbability === null ? '—' : `${(modelProbability * 100).toFixed(1)}%`}
          </p>
          <p className="mt-0.5 text-[10px] leading-tight text-text-faint">over this line</p>
        </div>
      </div>

      {/* Per-book prices at the selected threshold */}
      <ul className="mt-4 space-y-1.5">
        {selected.books.map((b) => {
          const style = bookStyle(b.book, isDark)
          const best = b.over_price !== null && b.over_price === selected.best_over
          return (
            <li key={b.book} className="flex items-center justify-between gap-3 text-xs">
              <BookSwatch book={b.book} isDark={isDark} />
              <span className="flex items-center gap-3 tabular">
                <span className={clsx(best ? 'font-bold' : 'text-text-muted')}
                  style={best ? { color: style.color } : undefined}>
                  {formatPrice(b.over_price)}
                </span>
                <span className="text-text-faint">/ {formatPrice(b.under_price)}</span>
              </span>
            </li>
          )
        })}
      </ul>

      <p className="mt-4 text-[11px] leading-relaxed text-text-faint">
        Over / under prices, best over highlighted. A difference between the book's
        implied percentage and the model's is a disagreement, not an edge — the
        books price in news this model never sees.
      </p>
    </div>
  )
}
