import type { PropsWithChildren, ReactNode } from 'react'
import clsx from 'clsx'

export function Card({
  children,
  className,
  padded = true,
}: PropsWithChildren<{ className?: string; padded?: boolean }>) {
  return (
    <div
      className={clsx(
        'rounded-2xl border border-border bg-surface/80 backdrop-blur-sm shadow-[0_1px_0_0_rgba(255,255,255,0.03)_inset]',
        padded && 'p-5 sm:p-6',
        className,
      )}
    >
      {children}
    </div>
  )
}

export function SectionHeading({
  title,
  subtitle,
  action,
}: {
  title: string
  subtitle?: string
  action?: ReactNode
}) {
  return (
    <div className="mb-4 flex items-start justify-between gap-4">
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-muted">{title}</h2>
        {subtitle && <p className="mt-1 text-xs text-text-faint">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}
