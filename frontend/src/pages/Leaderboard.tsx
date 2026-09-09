import { useMemo, useState } from 'react'
import { ChevronDownIcon, ChevronUpIcon, TrophyIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { Link } from 'react-router-dom'
import { Card, SectionHeading } from '../components/common/Card'
import { ErrorState } from '../components/common/ErrorState'
import { Skeleton } from '../components/common/Skeleton'
import { useAsync } from '../hooks/useAsync'
import { accountsEnabled } from '../lib/supabase'
import { fetchLeaderboard, useSession, type LeaderboardRow } from '../lib/account'
import { rankBoard, stakeShortfall, type SortKey } from '../lib/leaderboard'

/**
 * Two ways to be top of the board.
 *
 * Hits rewards being right often; return rewards being right when it paid.
 * They are deliberately different games — a grinder taking heavy favourites can
 * lead on hits while losing coins, and someone with one brave longshot can take
 * the return crown from a standing start. Ranking only one of them would make
 * the other style of picking pointless, so the table sorts by either.
 *
 * Return is profit over coins staked, not profit alone, which is why a small
 * bankroll is no disadvantage. The catch is that it flatters tiny samples — a
 * single 1-coin winner at +2000 is a 2000% return that risked nothing — so a
 * player has to have staked a minimum before it counts. The floor is on coins
 * staked rather than picks made: one genuinely large bet still qualifies, which
 * is the whole appeal of the return board.
 *
 * The ordering itself lives in lib/leaderboard.ts, where it is unit-tested.
 */

const NUMBER = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })

function coins(value: number): string {
  return `${value > 0 ? '+' : ''}${NUMBER.format(Math.round(value))}`
}

export default function Leaderboard() {
  const [sort, setSort] = useState<SortKey>('hits')
  const [dir, setDir] = useState<'desc' | 'asc'>('desc')
  const { session } = useSession()

  const board = useAsync(() => fetchLeaderboard(), [], accountsEnabled)

  const rows = useMemo(
    () => rankBoard(board.data ?? [], sort, dir),
    [board.data, sort, dir],
  )

  function onSort(key: SortKey) {
    if (key === sort) setDir((d) => (d === 'desc' ? 'asc' : 'desc'))
    else { setSort(key); setDir('desc') }
  }

  return (
    <div className="mx-auto max-w-[1400px] px-4 pb-24 pt-8 sm:px-6 lg:px-8">
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-2xl font-extrabold tracking-tight text-text sm:text-3xl">
          <TrophyIcon className="h-7 w-7 text-accent-soft" />
          Leaderboard
        </h1>
        <p className="mt-1.5 max-w-2xl text-sm text-text-muted">
          Everyone starts with 100 imaginary coins. Sort by <strong className="font-semibold text-text">hits</strong> to
          see who is right most often, or by <strong className="font-semibold text-text">return</strong> to see whose
          coins worked hardest. Picks lock at kickoff and are settled from the same
          game data the rest of the site runs on.
        </p>
      </div>

      {!accountsEnabled && (
        <Card>
          <SectionHeading title="Accounts aren't set up on this deployment" />
          <p className="max-w-2xl text-sm text-text-muted">
            The leaderboard needs a Supabase project to hold accounts and picks.
            Until one is configured, picks still work — they're kept privately in
            your browser on the{' '}
            <Link to="/picks" className="font-semibold text-accent-soft hover:underline">My Picks</Link>{' '}
            page. See <code className="rounded bg-surface-2 px-1 py-0.5 text-xs">supabase/schema.sql</code> and
            the README to turn accounts on.
          </p>
        </Card>
      )}

      {accountsEnabled && (
        <Card padded={false}>
          <div className="px-5 pt-5 sm:px-6">
            <SectionHeading
              title={`Standings${board.data ? ` (${board.data.length})` : ''}`}
              subtitle="Click a column heading to rank by it."
            />
          </div>

          {board.loading && <div className="px-5 pb-6 sm:px-6"><Skeleton className="h-64 w-full" /></div>}
          {board.error && <div className="px-5 pb-6 sm:px-6"><ErrorState message={board.error} /></div>}

          {board.data?.length === 0 && (
            <div className="px-5 pb-10 pt-2 text-center sm:px-6">
              <p className="text-sm font-semibold text-text">Nobody has picked yet</p>
              <p className="mx-auto mt-1 max-w-sm text-sm text-text-faint">
                The first ranked pick makes this table. Open a player, find a line
                you like, and stake some coins.
              </p>
              <Link
                to="/"
                className="mt-4 inline-flex rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-semibold text-accent-soft"
              >
                Go to the dashboard
              </Link>
            </div>
          )}

          {rows.length > 0 && (
            <div className="overflow-x-auto scroll-thin">
              <table className="w-full min-w-[560px] border-collapse text-sm">
                <thead>
                  <tr className="border-y border-border text-left text-[11px] uppercase tracking-wide text-text-faint">
                    <th scope="col" className="px-5 py-2.5 font-semibold sm:px-6">User</th>
                    <SortableHeader
                      label="Hits"
                      active={sort === 'hits'}
                      dir={dir}
                      onClick={() => onSort('hits')}
                    />
                    <SortableHeader
                      label="Return"
                      active={sort === 'return'}
                      dir={dir}
                      onClick={() => onSort('return')}
                    />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <Row
                      key={row.user_id}
                      row={row}
                      rank={index + 1}
                      isMe={row.user_id === session?.user.id}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {rows.length > 0 && (
            <p className="px-5 py-4 text-[11px] leading-relaxed text-text-faint sm:px-6">
              Return is profit measured against coins staked, so a big win on a
              small stake counts for as much as a small win on a big one. It shows
              once a player has staked{' '}
              {NUMBER.format(rows[0]?.roi_threshold ?? 25)} coins in settled picks — long enough
              to mean something, short enough that one bold pick can still take the
              top spot. A pick voids, returning its stake, if the player didn't
              record a stat line.
            </p>
          )}
        </Card>
      )}
    </div>
  )
}

function SortableHeader({
  label, active, dir, onClick,
}: { label: string; active: boolean; dir: 'desc' | 'asc'; onClick: () => void }) {
  return (
    <th
      scope="col"
      aria-sort={active ? (dir === 'desc' ? 'descending' : 'ascending') : 'none'}
      className="px-3 py-2.5 text-right font-semibold"
    >
      <button
        type="button"
        onClick={onClick}
        className={clsx(
          'ml-auto flex items-center gap-1 rounded px-1.5 py-1 text-[11px] font-semibold uppercase tracking-wide transition-colors',
          active ? 'text-text' : 'text-text-faint hover:text-text-muted',
        )}
      >
        {label}
        {active
          ? dir === 'desc'
            ? <ChevronDownIcon className="h-3.5 w-3.5" />
            : <ChevronUpIcon className="h-3.5 w-3.5" />
          : <ChevronDownIcon className="h-3.5 w-3.5 opacity-30" />}
      </button>
    </th>
  )
}

function Row({ row, rank, isMe }: { row: LeaderboardRow; rank: number; isMe: boolean }) {
  const settled = row.hits + row.misses
  return (
    <tr className={clsx('border-b border-border/60 last:border-0', isMe && 'bg-accent/5')}>
      <td className="px-5 py-3 sm:px-6">
        <span className="tabular mr-3 text-xs font-semibold text-text-faint">{rank}</span>
        <span className="font-semibold text-text">{row.username}</span>
        {isMe && (
          <span className="ml-2 rounded-full border border-accent/30 bg-accent/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-accent-soft">
            You
          </span>
        )}
        <span className="block text-xs text-text-faint">
          {NUMBER.format(Math.round(row.balance))} coins
          {row.pending > 0 && ` · ${row.pending} pending`}
        </span>
      </td>

      <td className="px-3 py-3 text-right">
        <span className="tabular font-semibold text-text">{row.hits}</span>
        <span className="block text-xs text-text-faint">
          {settled > 0 ? `of ${settled} settled` : 'no results yet'}
        </span>
      </td>

      <td className="px-3 py-3 text-right">
        {row.roi === null ? (
          <>
            <span className="tabular font-semibold text-text-faint">—</span>
            <span className="block text-xs text-text-faint">
              {NUMBER.format(stakeShortfall(row))} more staked
            </span>
          </>
        ) : (
          <>
            <span className={clsx(
              'tabular font-semibold',
              row.roi > 0 ? 'text-over' : row.roi < 0 ? 'text-under' : 'text-text',
            )}>
              {row.roi > 0 ? '+' : ''}{(row.roi * 100).toFixed(1)}%
            </span>
            <span className="block text-xs text-text-faint">
              {coins(row.profit)} on {NUMBER.format(Math.round(row.staked))} staked
            </span>
          </>
        )}
      </td>
    </tr>
  )
}
