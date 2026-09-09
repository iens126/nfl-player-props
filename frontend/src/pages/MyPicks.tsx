import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDownTrayIcon, ArrowUpTrayIcon, TrashIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { api } from '../api/client'
import { Card, SectionHeading } from '../components/common/Card'
import { ErrorState } from '../components/common/ErrorState'
import { Skeleton } from '../components/common/Skeleton'
import { StatCard } from '../components/player/StatCard'
import { statLabel } from '../lib/statLabels'
import {
  clearPicks, deletePick, exportPicks, gradePick, importPicks, loadPicks,
  summarise, STARTING_BANKROLL, type BankrollSummary, type GradedPick, type PickStatus,
} from '../lib/picks'
import { accountsEnabled } from '../lib/supabase'
import { ACCOUNT_BANKROLL, useAccountPicks, useProfile, type AccountPick } from '../lib/account'

/**
 * Every pick a user has made, settled against results as they arrive.
 *
 * There are two records here and they are kept apart on purpose.
 *
 * **Ranked** picks belong to an account. They were priced by the server off
 * the live board, they locked at kickoff, and they are settled by the nightly
 * job — which is what makes them comparable with other people's on the
 * leaderboard. They cannot be edited or deleted; a record you can rewrite
 * isn't a record.
 *
 * **In this browser** is the private tracker: any line, any price, delete
 * whatever you like. It predates accounts and still works without one.
 *
 * The private ones are deliberately *not* migrated into an account. Their
 * lines, prices and timestamps were never checked by anything, so importing
 * them would put unverified picks on a public board. A clean start is the
 * honest option.
 */

const STATUS_STYLE: Record<PickStatus, { label: string; className: string }> = {
  hit: { label: 'Hit', className: 'bg-over/15 text-over border-over/30' },
  miss: { label: 'Miss', className: 'bg-under/15 text-under border-under/30' },
  pending: { label: 'Pending', className: 'bg-surface-3 text-text-muted border-border' },
  void: { label: 'Void', className: 'bg-warn/15 text-warn border-warn/30' },
}

type Filter = 'all' | 'pending' | 'settled'
type Source = 'ranked' | 'local'

const FILTERS: Filter[] = ['all', 'pending', 'settled']

function keeps(status: PickStatus, filter: Filter): boolean {
  if (filter === 'all') return true
  if (filter === 'pending') return status === 'pending'
  return status === 'hit' || status === 'miss'
}

export default function MyPicks() {
  const { profile } = useProfile()
  const canRank = accountsEnabled && Boolean(profile)
  const [source, setSource] = useState<Source>('ranked')

  // Falls back the moment ranking isn't available, so a signed-out visitor
  // never lands on an empty tab they can't do anything about.
  const active: Source = canRank ? source : 'local'

  return (
    <div className="mx-auto max-w-[1400px] px-4 pb-24 pt-8 sm:px-6 lg:px-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-text sm:text-3xl">My Picks</h1>
          <p className="mt-1.5 max-w-2xl text-sm text-text-muted">
            {active === 'ranked'
              ? 'Picks priced from the live board and locked at kickoff. They settle automatically as games are played and count towards the leaderboard.'
              : 'Lines you\'ve tracked, settled against results as games are played. Coins are imaginary and stay in this browser — there\'s no account, nothing to buy and nothing to cash out.'}
          </p>
        </div>

        {canRank && (
          <div className="flex gap-1 rounded-lg bg-surface-2 p-1">
            {([['ranked', 'Ranked'], ['local', 'In this browser']] as [Source, string][]).map(
              ([key, label]) => (
                <button
                  key={key}
                  onClick={() => setSource(key)}
                  className={clsx(
                    'rounded-md px-2.5 py-1 text-xs font-semibold transition-colors',
                    active === key ? 'bg-accent text-white' : 'text-text-muted hover:text-text',
                  )}
                >
                  {label}
                </button>
              ),
            )}
          </div>
        )}
      </div>

      {accountsEnabled && !canRank && (
        <Card className="mb-6">
          <SectionHeading title="Play for a place on the leaderboard" />
          <p className="max-w-2xl text-sm text-text-muted">
            Sign in from the menu at the top right and choose a username to get 100
            coins and a ranked record. Your picks below stay exactly where they are
            — a ranked bankroll starts fresh, because these ones were never priced
            against a real board.{' '}
            <Link to="/leaderboard" className="font-semibold text-accent-soft hover:underline">
              See the standings
            </Link>.
          </p>
        </Card>
      )}

      {active === 'ranked' ? <RankedPicks /> : <LocalPicks />}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Ranked
// ---------------------------------------------------------------------------

function RankedPicks() {
  const { picks, summary, loading, error } = useAccountPicks()
  const [filter, setFilter] = useState<Filter>('all')

  const visible = (picks ?? []).filter((p) => keeps(p.settlement?.status ?? 'pending', filter))

  return (
    <>
      <Summary summary={summary} starting={ACCOUNT_BANKROLL} />

      <Card padded={false}>
        <Toolbar
          title={`Ranked picks${picks ? ` (${picks.length})` : ''}`}
          filter={filter}
          onFilter={setFilter}
        />

        {loading && <div className="px-5 pb-5 sm:px-6"><Skeleton className="h-40 w-full" /></div>}
        {error && <div className="px-5 pb-5 sm:px-6"><ErrorState message={error} /></div>}

        {picks?.length === 0 && (
          <Empty
            title="No ranked picks yet"
            body="Open a player on the dashboard, find a line you like, and stake some coins. The price is taken from the board when you place it."
          />
        )}

        {visible.length > 0 && (
          <div className="overflow-x-auto scroll-thin">
            <table className="w-full min-w-[860px] border-collapse text-sm">
              <Headings />
              <tbody>
                {visible.map((pick) => <RankedRow key={pick.id} pick={pick} />)}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <p className="mt-4 text-[11px] leading-relaxed text-text-faint">
        Ranked picks can't be edited or deleted — a record you can rewrite isn't a
        record. A pick voids and returns its stake if the player didn't record a
        stat line. Results follow the daily data refresh, so a Sunday game usually
        settles on Monday and a Monday night game on Wednesday.
      </p>
    </>
  )
}

function RankedRow({ pick }: { pick: AccountPick }) {
  const status = pick.settlement?.status ?? 'pending'
  const profit = pick.settlement?.profit ?? 0
  const kickoff = new Date(pick.kickoff)

  return (
    <tr className="border-b border-border/60 last:border-0">
      <td className="px-5 py-3 sm:px-6">
        <span className="font-semibold text-text">{pick.player}</span>
        <span className="ml-1.5 text-text-muted">
          {pick.side} {pick.line} {statLabel(pick.stat)}
        </span>
        <span className="block text-xs text-text-faint">
          {pick.team} vs {pick.opponent}
          {pick.settlement?.week
            ? ` · Week ${pick.settlement.week}`
            : ` · ${kickoff.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`}
          {pick.book ? ` · ${pick.book}` : ''}
        </span>
      </td>
      <td className="px-3 py-3 text-right tabular text-text-muted">{pick.stake.toLocaleString()}</td>
      <td className="px-3 py-3 text-right tabular text-text-muted">
        {pick.price > 0 ? `+${pick.price}` : pick.price}
      </td>
      <td className="px-3 py-3 text-right tabular text-text">{pick.settlement?.actual ?? '—'}</td>
      <td className={clsx(
        'px-3 py-3 text-right tabular font-semibold',
        profit > 0 ? 'text-over' : profit < 0 ? 'text-under' : 'text-text-faint',
      )}>
        {status === 'hit' || status === 'miss'
          ? `${profit > 0 ? '+' : ''}${Math.round(profit).toLocaleString()}`
          : '—'}
      </td>
      <td className="px-3 py-3 text-center">
        <StatusPill status={status} />
      </td>
      <td className="px-3 py-3" />
    </tr>
  )
}

// ---------------------------------------------------------------------------
// This browser
// ---------------------------------------------------------------------------

function LocalPicks() {
  const [graded, setGraded] = useState<GradedPick[] | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  const [notice, setNotice] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const refresh = useCallback(async () => {
    const picks = loadPicks()
    // One fetch per distinct player, not per pick. Always resolved through the
    // same await so state is set once, asynchronously, on every path.
    const names = [...new Set(picks.map((p) => p.player))]
    const logs = new Map<string, Awaited<ReturnType<typeof api.playerGames>>>()
    await Promise.all(names.map(async (name) => {
      try {
        logs.set(name, await api.playerGames(name))
      } catch {
        // A player whose file can't be read simply stays pending.
        logs.set(name, [])
      }
    }))
    setGraded(picks.map((p) => gradePick(p, logs.get(p.player) ?? [])))
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  function onDelete(id: string) {
    deletePick(id)
    void refresh()
  }

  function onExport() {
    const blob = new Blob([exportPicks()], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `gridedge-picks-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function onImport(file: File) {
    try {
      const { added, skipped } = importPicks(await file.text())
      setNotice(`Imported ${added} pick${added === 1 ? '' : 's'}${skipped ? `, skipped ${skipped} already saved` : ''}.`)
      void refresh()
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'That file could not be read.')
    }
  }

  const summary = summarise(graded ?? [])
  const visible = (graded ?? []).filter((p) => keeps(p.status, filter))

  return (
    <>
      <div className="mb-4 flex justify-end gap-2">
        <button
          type="button"
          onClick={onExport}
          disabled={!graded?.length}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-text-muted transition-colors hover:bg-surface-2 disabled:opacity-40"
        >
          <ArrowDownTrayIcon className="h-3.5 w-3.5" /> Export
        </button>
        <button
          type="button"
          onClick={() => fileInput.current?.click()}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-text-muted transition-colors hover:bg-surface-2"
        >
          <ArrowUpTrayIcon className="h-3.5 w-3.5" /> Import
        </button>
        <input
          ref={fileInput}
          type="file"
          accept="application/json"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) void onImport(file)
            e.target.value = ''
          }}
        />
      </div>

      {notice && (
        <p className="mb-4 rounded-xl border border-border bg-surface-2 px-4 py-2.5 text-sm text-text-muted">
          {notice}
        </p>
      )}

      <Summary summary={summary} starting={STARTING_BANKROLL} />

      <Card padded={false}>
        <Toolbar
          title={`Tracked picks${graded ? ` (${graded.length})` : ''}`}
          filter={filter}
          onFilter={setFilter}
        />

        {graded === null && <div className="px-5 pb-5 sm:px-6"><Skeleton className="h-40 w-full" /></div>}

        {graded?.length === 0 && (
          <Empty
            title="No picks tracked yet"
            body="Open a player on the dashboard, enter a line, and use “Track this pick” to follow it here."
          />
        )}

        {visible.length > 0 && (
          <div className="overflow-x-auto scroll-thin">
            <table className="w-full min-w-[860px] border-collapse text-sm">
              <Headings />
              <tbody>
                {visible.map((p) => (
                  <tr key={p.id} className="border-b border-border/60 last:border-0">
                    <td className="px-5 py-3 sm:px-6">
                      <span className="font-semibold text-text">{p.player}</span>
                      <span className="ml-1.5 text-text-muted">
                        {p.side} {p.line} {statLabel(p.stat)}
                      </span>
                      <span className="block text-xs text-text-faint">
                        {p.team} vs {p.opponent}
                        {p.week ? ` · Week ${p.week}` : ''}
                        {p.book ? ` · ${p.book}` : ''}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-right tabular text-text-muted">
                      {p.stake.toLocaleString()}
                    </td>
                    <td className="px-3 py-3 text-right tabular text-text-muted">
                      {p.price > 0 ? `+${p.price}` : p.price}
                    </td>
                    <td className="px-3 py-3 text-right tabular text-text">{p.actual ?? '—'}</td>
                    <td className={clsx(
                      'px-3 py-3 text-right tabular font-semibold',
                      p.profit > 0 ? 'text-over' : p.profit < 0 ? 'text-under' : 'text-text-faint',
                    )}>
                      {p.status === 'hit' || p.status === 'miss'
                        ? `${p.profit > 0 ? '+' : ''}${Math.round(p.profit).toLocaleString()}`
                        : '—'}
                    </td>
                    <td className="px-3 py-3 text-center"><StatusPill status={p.status} /></td>
                    <td className="px-3 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => onDelete(p.id)}
                        aria-label={`Delete ${p.player} pick`}
                        className="rounded p-1 text-text-faint transition-colors hover:bg-surface-2 hover:text-under"
                      >
                        <TrashIcon className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {(graded?.length ?? 0) > 0 && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <p className="text-[11px] leading-relaxed text-text-faint">
            A pick voids if the player didn't record a stat line that week, rather
            than counting as a loss. ROI is measured against coins staked — a high
            win rate on heavy favourites can still lose money.
          </p>
          <button
            type="button"
            onClick={() => {
              if (confirm('Delete every tracked pick? This cannot be undone.')) {
                clearPicks()
                void refresh()
              }
            }}
            className="shrink-0 rounded-lg border border-under/30 px-3 py-1.5 text-xs font-semibold text-under transition-colors hover:bg-under/10"
          >
            Clear all picks
          </button>
        </div>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Shared furniture
// ---------------------------------------------------------------------------

function Summary({ summary, starting }: { summary: BankrollSummary; starting: number }) {
  return (
    <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      <StatCard
        label="Balance"
        value={Math.round(summary.balance).toLocaleString()}
        sublabel={`${Math.round(summary.available).toLocaleString()} available`}
        tone={summary.balance >= starting ? 'over' : 'under'}
      />
      <StatCard
        label="Record"
        value={summary.settled ? `${summary.hits}-${summary.misses}` : '—'}
        sublabel={summary.voids ? `${summary.voids} void` : 'hits – misses'}
      />
      <StatCard
        label="Win Rate"
        value={summary.winRate === null ? '—' : `${(summary.winRate * 100).toFixed(0)}%`}
        sublabel={`${summary.settled} settled`}
      />
      <StatCard
        label="Return"
        value={summary.roi === null ? '—' : `${(summary.roi * 100).toFixed(1)}%`}
        sublabel="on coins staked"
        tone={summary.roi === null ? 'neutral' : summary.roi >= 0 ? 'over' : 'under'}
      />
      <StatCard
        label="Pending"
        value={summary.pending}
        sublabel={`${Math.round(summary.atRisk).toLocaleString()} at risk`}
      />
    </div>
  )
}

function Toolbar({
  title, filter, onFilter,
}: { title: string; filter: Filter; onFilter: (f: Filter) => void }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-5 sm:px-6">
      <SectionHeading title={title} />
      <div className="mb-4 flex gap-1 rounded-lg bg-surface-2 p-1">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => onFilter(f)}
            className={clsx(
              'rounded-md px-2.5 py-1 text-xs font-semibold capitalize transition-colors',
              filter === f ? 'bg-accent text-white' : 'text-text-muted hover:text-text',
            )}
          >
            {f}
          </button>
        ))}
      </div>
    </div>
  )
}

function Headings() {
  return (
    <thead>
      <tr className="border-y border-border text-left text-[11px] uppercase tracking-wide text-text-faint">
        <th className="px-5 py-2.5 font-semibold sm:px-6">Pick</th>
        <th className="px-3 py-2.5 text-right font-semibold">Stake</th>
        <th className="px-3 py-2.5 text-right font-semibold">Price</th>
        <th className="px-3 py-2.5 text-right font-semibold">Actual</th>
        <th className="px-3 py-2.5 text-right font-semibold">P&amp;L</th>
        <th className="px-3 py-2.5 text-center font-semibold">Status</th>
        <th className="px-3 py-2.5" />
      </tr>
    </thead>
  )
}

function StatusPill({ status }: { status: PickStatus }) {
  return (
    <span className={clsx(
      'inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide',
      STATUS_STYLE[status].className,
    )}>
      {STATUS_STYLE[status].label}
    </span>
  )
}

function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="px-5 pb-10 pt-4 text-center sm:px-6">
      <p className="text-sm font-semibold text-text">{title}</p>
      <p className="mx-auto mt-1 max-w-sm text-sm text-text-faint">{body}</p>
      <Link
        to="/"
        className="mt-4 inline-flex rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-semibold text-accent-soft"
      >
        Go to the dashboard
      </Link>
    </div>
  )
}
