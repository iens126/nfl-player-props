import type { ReactNode } from 'react'
import clsx from 'clsx'

/**
 * One headline number in the stat strip.
 *
 * Cards sit shoulder to shoulder in a grid, so they are built to line up:
 * a fixed-height label row, the value on a shared baseline, and the caption
 * pinned to the bottom. Without that, a card carrying a caption pushed its
 * value up relative to its neighbours and the row read as ragged.
 *
 * Word values get a smaller type size than numbers. "MEDIUM" at the numeric
 * size overflowed its box at every breakpoint where six cards share a row.
 */
export function StatCard({
  label,
  value,
  sublabel,
  tone = 'neutral',
  icon,
}: {
  label: string
  value: ReactNode
  /** Caption under the value — e.g. what window an average covers. */
  sublabel?: string
  tone?: 'neutral' | 'accent' | 'over' | 'under'
  icon?: ReactNode
}) {
  const valueTone = {
    neutral: 'text-text',
    accent: 'text-accent-soft',
    over: 'text-over',
    under: 'text-under',
  }[tone]

  // Ratings like HIGH / MEDIUM / LOW are words, not figures, and need room.
  const isWord = typeof value === 'string' && /[A-Za-z]{3,}/.test(value)

  return (
    <div className="flex flex-col rounded-2xl border border-border bg-surface p-3.5 sm:p-4">
      <div className="flex min-h-[16px] items-start justify-between gap-1">
        <span className="text-[10px] font-semibold uppercase leading-tight tracking-wider text-text-faint">
          {label}
        </span>
        {icon}
      </div>

      <div
        className={clsx(
          'mt-1.5 font-extrabold tabular tracking-tight',
          isWord ? 'text-base sm:text-lg' : 'text-2xl sm:text-[26px]',
          valueTone,
        )}
      >
        {value}
      </div>

      {/* Always rendered so every card in a row shares the same baseline. */}
      <p className="mt-auto pt-1 text-[10px] leading-tight text-text-faint">
        {sublabel ?? ' '}
      </p>
    </div>
  )
}
