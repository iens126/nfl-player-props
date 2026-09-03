import clsx from 'clsx'
import { bookStyle } from '../../lib/bookStyle'

/**
 * A sportsbook's name with a colour-coded monogram.
 *
 * Colour and initials only — no logos or wordmarks. Sportsbook marks are
 * registered trademarks licensed to affiliates under brand agreements, and
 * putting them on an unaffiliated analytics site would both risk a trademark
 * complaint and imply a partnership that doesn't exist. A consistent colour per
 * book gives the same at-a-glance recognition in a dense table.
 */
export function BookSwatch({
  book,
  isDark,
  className,
}: {
  book: string
  isDark: boolean
  className?: string
}) {
  const { color, initials } = bookStyle(book, isDark)

  return (
    <span className={clsx('inline-flex items-center gap-1.5', className)}>
      <span
        aria-hidden="true"
        className="inline-flex h-4 w-6 shrink-0 items-center justify-center rounded text-[9px] font-bold tracking-tight text-white"
        style={{ background: color }}
      >
        {initials}
      </span>
      <span className="font-semibold text-text">{book}</span>
    </span>
  )
}
