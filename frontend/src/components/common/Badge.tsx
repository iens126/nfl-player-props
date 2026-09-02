import type { PropsWithChildren } from 'react'
import clsx from 'clsx'

type Tone = 'neutral' | 'accent' | 'over' | 'under' | 'warn' | 'high' | 'medium' | 'low'

const TONE_CLASSES: Record<Tone, string> = {
  neutral: 'bg-surface-3 text-text-muted border-border',
  accent: 'bg-accent/15 text-accent-soft border-accent/30',
  over: 'bg-over/15 text-over border-over/30',
  under: 'bg-under/15 text-under border-under/30',
  warn: 'bg-warn/15 text-warn border-warn/30',
  high: 'bg-over/15 text-over border-over/30',
  medium: 'bg-warn/15 text-warn border-warn/30',
  low: 'bg-under/15 text-under border-under/30',
}

export function Badge({
  children,
  tone = 'neutral',
  className,
}: PropsWithChildren<{ tone?: Tone; className?: string }>) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide',
        TONE_CLASSES[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

export function stabilityTone(rating: string | null | undefined): Tone {
  if (rating === 'HIGH') return 'high'
  if (rating === 'MEDIUM') return 'medium'
  if (rating === 'LOW') return 'low'
  return 'neutral'
}
