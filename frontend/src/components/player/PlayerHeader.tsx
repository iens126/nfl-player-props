import { UserCircleIcon } from '@heroicons/react/24/solid'
import type { PlayerSummary, Team } from '../../api/types'

export function PlayerHeader({
  summary,
  opponent,
}: {
  summary: PlayerSummary
  opponent: Team | null
}) {
  return (
    <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
      <div className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-border bg-surface-2 sm:h-24 sm:w-24">
        {summary.headshot_url ? (
          <img
            src={summary.headshot_url}
            alt={summary.name}
            className="h-full w-full object-cover"
            onError={(e) => {
              ;(e.currentTarget as HTMLImageElement).style.display = 'none'
            }}
          />
        ) : (
          <UserCircleIcon className="h-14 w-14 text-text-faint" />
        )}
      </div>

      <div className="min-w-0">
        <h1 className="truncate text-2xl font-extrabold tracking-tight text-text sm:text-3xl">{summary.name}</h1>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-text-muted">
          <span className="rounded-md bg-surface-2 px-2 py-0.5 font-semibold text-text">{summary.team}</span>
          <span>•</span>
          <span className="font-medium">{summary.position}</span>
          {opponent && (
            <>
              <span>•</span>
              <span>
                vs{' '}
                <span className="font-semibold text-text">{opponent.abbr}</span>
              </span>
            </>
          )}
          <span>•</span>
          <span>{summary.games_played} games played</span>
        </div>
      </div>
    </div>
  )
}
