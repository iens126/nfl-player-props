import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDownTrayIcon, ArrowUpTrayIcon, TrashIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { api } from '../api/client'
import { Card, SectionHeading } from '../components/common/Card'
import { Skeleton } from '../components/common/Skeleton'
import { StatCard } from '../components/player/StatCard'
import { statLabel } from '../lib/statLabels'
import {
  clearPicks, deletePick, exportPicks, gradePick, importPicks, loadPicks,
  summarise, type GradedPick, type PickStatus,
} from '../lib/picks'

/**
 * Every saved pick, settled against results as they arrive.
 *
 * Grading needs no server: the daily data bundle already carries each player's
 * weekly game log, so a pick resolves by looking up the week it was made for.
 * Picks that are still ahead of us stay pending; a player who didn't suit up
 * voids rather than losing, the way a sportsbook would treat it.
 */

const STATUS_STYLE: Record<PickStatus, { label: string; className: string }> = {
  hit: { label: 'Hit', className: 'bg-over/15 text-over border-over/30' },
  miss: { label: 'Miss', className: 'bg-under/15 text-under border-under/30' },
  pending: { label: 'Pending', className: 'bg-surface-3 text-text-muted border-border' },
  void: { label: 'Void', className: 'bg-warn/15 text-warn border-warn/30' },
}

type Filter = 'all' | 'pending' | 'settled'

export default function MyPicks() {
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
  const visible = (graded ?? []).filter((p) =>
    filter === 'all' ? true
      : filter === 'pending' ? p.status === 'pending'
        : p.status === 'hit' || p.status === 'miss')

  return (
    <div className="mx-auto max-w-[1400px] px-4 pb-24 pt-8 sm:px-6 lg:px-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-text sm:text-3xl">My Picks</h1>
          <p className="mt-1.5 max-w-2xl text-sm text-text-muted">
            Lines you've tracked, settled against results as games are played. Coins
            are imaginary and stay in this browser — there's no account, nothing to
            buy and nothing to cash out.
          </p>
        </div>
        <div className="flex gap-2">
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
      </div>

      {notice && (
        <p className="mb-4 rounded-xl border border-border bg-surface-2 px-4 py-2.5 text-sm text-text-muted">
          {notice}
        </p>
      )}

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard
          label="Balance"
          value={Math.round(summary.balance).toLocaleString()}
          sublabel={`${Math.round(summary.available).toLocaleString()} available`}
          tone={summary.balance >= 10_000 ? 'over' : 'under'}
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
          label="ROI"
          value={summary.roi === null ? '—' : `${(summary.roi * 100).toFixed(1)}%`}
          sublabel="return on coins staked"
          tone={summary.roi !== null && summary.roi >= 0 ? 'over' : 'under'}
        />
        <StatCard
          label="Pending"
          value={summary.pending}
          sublabel={`${Math.round(summary.atRisk).toLocaleString()} at risk`}
        />
      </div>

      <Card padded={false}>
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-5 sm:px-6">
          <SectionHeading title={`Tracked picks${graded ? ` (${graded.length})` : ''}`} />
          <div className="mb-4 flex gap-1 rounded-lg bg-surface-2 p-1">
            {(['all', 'pending', 'settled'] as Filter[]).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
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

        {graded === null && <div className="px-5 pb-5 sm:px-6"><Skeleton className="h-40 w-full" /></div>}

        {graded?.length === 0 && (
          <div className="px-5 pb-10 pt-4 text-center sm:px-6">
            <p className="text-sm font-semibold text-text">No picks tracked yet</p>
            <p className="mx-auto mt-1 max-w-sm text-sm text-text-faint">
              Open a player on the dashboard, enter a line, and use “Track this pick”
              to follow it here.
            </p>
            <Link
              to="/"
              className="mt-4 inline-flex rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-semibold text-accent-soft"
            >
              Go to the dashboard
            </Link>
          </div>
        )}

        {visible.length > 0 && (
          <div className="overflow-x-auto scroll-thin">
            <table className="w-full min-w-[860px] border-collapse text-sm">
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
                    <td className="px-3 py-3 text-right tabular text-text">
                      {p.actual ?? '—'}
                    </td>
                    <td className={clsx(
                      'px-3 py-3 text-right tabular font-semibold',
                      p.profit > 0 ? 'text-over' : p.profit < 0 ? 'text-under' : 'text-text-faint',
                    )}>
                      {p.status === 'hit' || p.status === 'miss'
                        ? `${p.profit > 0 ? '+' : ''}${Math.round(p.profit).toLocaleString()}`
                        : '—'}
                    </td>
                    <td className="px-3 py-3 text-center">
                      <span className={clsx(
                        'inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide',
                        STATUS_STYLE[p.status].className,
                      )}>
                        {STATUS_STYLE[p.status].label}
                      </span>
                    </td>
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
    </div>
  )
}
