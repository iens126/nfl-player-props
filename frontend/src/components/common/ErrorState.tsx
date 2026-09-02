import clsx from 'clsx'
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline'

export function ErrorState({ message, compact = false }: { message: string; compact?: boolean }) {
  return (
    <div
      role="alert"
      className={clsx(
        'flex items-center gap-3 rounded-xl border border-under/25 bg-under/5',
        compact ? 'p-3' : 'p-4',
      )}
    >
      <ExclamationTriangleIcon className="h-5 w-5 shrink-0 text-under" />
      <p className="text-sm text-text-muted">{message}</p>
    </div>
  )
}
