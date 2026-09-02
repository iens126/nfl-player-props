import type { ReactNode } from 'react'
import clsx from 'clsx'

export function StatCard({
  label,
  value,
  sublabel,
  tone = 'neutral',
  icon,
}: {
  label: string
  value: ReactNode
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

  return (
    <div className="rounded-2xl border border-border bg-surface p-4 sm:p-5">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-text-faint">{label}</span>
        {icon}
      </div>
      <div className={clsx('mt-2 text-2xl font-extrabold tabular tracking-tight sm:text-[26px]', valueTone)}>
        {value}
      </div>
      {sublabel && <p className="mt-1 text-xs text-text-faint">{sublabel}</p>}
    </div>
  )
}
