import clsx from 'clsx'

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx('skeleton rounded-lg', className)} />
}

export function SkeletonCard() {
  return (
    <div className="rounded-2xl border border-border bg-surface p-5 sm:p-6">
      <Skeleton className="h-3 w-24 mb-4" />
      <Skeleton className="h-8 w-32 mb-2" />
      <Skeleton className="h-3 w-20" />
    </div>
  )
}
