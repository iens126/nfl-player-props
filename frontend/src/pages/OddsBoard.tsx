import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowTopRightOnSquareIcon, ArrowRightIcon } from '@heroicons/react/24/outline'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { Card, SectionHeading } from '../components/common/Card'
import { Skeleton } from '../components/common/Skeleton'
import { ErrorState } from '../components/common/ErrorState'
import { OddsFreshness } from '../components/player/OddsFreshness'
import { bookStyle } from '../lib/bookStyle'
import { useTheme } from '../lib/theme'
import { statLabel } from '../lib/statLabels'
import type { BookLine, OddsBoardEntry } from '../api/types'

// Markets The Odds API carries for NFL player props, in the order people
// usually look for them.
const STAT_OPTIONS = [
  'receiving_yards', 'receptions', 'rushing_yards', 'passing_yards',
  'carries', 'passing_tds', 'receiving_tds', 'rushing_tds',
  'attempts', 'completions', 'passing_interceptions',
]

function formatPrice(price: number | null) {
  if (price === null || price === undefined) return '—'
  return price > 0 ? `+${price}` : `${price}`
}

function formatKickoff(iso: string | null) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    weekday: 'short', month: 'numeric', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
  })
}

/**
 * A plain list of what the books are currently offering.
 *
 * Deliberately not a recommendation engine: nothing here is scored, ranked by
 * "value", or flagged as a good bet. It shows the lines, and every row links
 * through to that player's history and projection so someone can do their own
 * homework on anything that catches their eye.
 */
export default function OddsBoard() {
  const navigate = useNavigate()
  const { theme } = useTheme()
  const isDark = theme === 'dark'
  const [stat, setStat] = useState('receiving_yards')
  const [eventId, setEventId] = useState<string | null>(null)

  const games = useAsync(() => api.oddsGames(), [])

  // Until the user picks one, show the next game on the slate. Derived rather
  // than stored, so there's no render pass where nothing is selected.
  const selectedEvent = eventId ?? games.data?.games?.[0]?.id ?? null

  const board = useAsync(
    () => api.oddsBoard(selectedEvent!, stat),
    [selectedEvent, stat],
    !!selectedEvent,
  )

  const bookNames = useMemo(() => {
    const names = new Set<string>()
    board.data?.entries.forEach((e) => e.books.forEach((b) => names.add(b.book)))
    return Array.from(names).sort()
  }, [board.data])

  const notConfigured = games.data?.status === 'not_configured'

  function openPlayer(entry: OddsBoardEntry) {
    const params = new URLSearchParams({ player: entry.player, stat })
    if (entry.consensus_line !== null) params.set('line', String(entry.consensus_line))
    // Carry the matchup this line came from. Without it the dashboard falls
    // back to guessing the player's next scheduled opponent, which is wrong
    // whenever you're looking at a game that isn't their next one.
    if (entry.opponent) params.set('opponent', entry.opponent)
    navigate(`/?${params.toString()}`)
  }

  return (
    <div className="mx-auto max-w-7xl px-4 pb-24 pt-8 sm:px-6 lg:px-8">
      <div className="mb-6">
        <h1 className="text-2xl font-extrabold tracking-tight text-text sm:text-3xl">Odds Board</h1>
        <p className="mt-1.5 max-w-3xl text-sm text-text-muted">
          Live player prop lines from the major sportsbooks. Browse what's on offer, and open any
          player to see their game history and the model's read on that number.
        </p>
      </div>

      {notConfigured ? (
        <Card>
          <SectionHeading title="Live odds not configured" />
          <p className="text-sm leading-relaxed text-text-muted">
            {games.data?.message} The rest of the app works without it — odds are an optional
            add-on. Set <code className="rounded bg-surface-2 px-1.5 py-0.5 text-xs">ODDS_API_KEY</code>{' '}
            on the backend to switch this on.
          </p>
          <a
            href="https://the-odds-api.com/"
            target="_blank"
            rel="noreferrer"
            className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-accent-soft underline underline-offset-2"
          >
            Get a free API key
            <ArrowTopRightOnSquareIcon className="h-3.5 w-3.5" />
          </a>
        </Card>
      ) : (
        <>
          <Card className="mb-6">
            <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-text-faint">
                  Game
                </label>
                <select
                  className="w-full rounded-xl border border-border bg-surface-2 px-3.5 py-2.5 text-sm text-text outline-none focus:border-accent"
                  value={selectedEvent ?? ''}
                  onChange={(e) => setEventId(e.target.value)}
                  disabled={games.loading || !games.data?.games?.length}
                >
                  {games.loading && <option>Loading games…</option>}
                  {!games.loading && !games.data?.games?.length && <option>No games listed</option>}
                  {games.data?.games?.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.away_team} @ {g.home_team} · {formatKickoff(g.commence_time)}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-text-faint">
                  Stat Category
                </label>
                <select
                  className="w-full rounded-xl border border-border bg-surface-2 px-3.5 py-2.5 text-sm text-text outline-none focus:border-accent"
                  value={stat}
                  onChange={(e) => setStat(e.target.value)}
                >
                  {STAT_OPTIONS.map((s) => (
                    <option key={s} value={s}>{statLabel(s)}</option>
                  ))}
                </select>
              </div>
            </div>
            <p className="mt-3 text-xs text-text-faint">
              Each game + stat combination costs one API credit and is cached for 10 minutes.
            </p>
          </Card>

          {games.error && <ErrorState message={games.error} />}
          {board.loading && (
            <Card>
              <Skeleton className="mb-3 h-5 w-48" />
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="mb-2 h-10 w-full" />
              ))}
            </Card>
          )}
          {board.error && <ErrorState message={board.error} />}

          {board.data && board.data.status !== 'ok' && (
            <Card>
              <p className="text-sm leading-relaxed text-text-muted">{board.data.message}</p>
            </Card>
          )}

          {board.data?.status === 'ok' && (
            <Card padded={false}>
              <div className="flex flex-wrap items-baseline justify-between gap-2 px-5 pt-5 sm:px-6">
                <SectionHeading
                  title={`${statLabel(stat)} — ${board.data.entries.length} players`}
                  subtitle={
                    board.data.game
                      ? `${board.data.game.away_team} @ ${board.data.game.home_team}`
                      : undefined
                  }
                />
              </div>

              <div className="overflow-x-auto scroll-thin">
                <table className="w-full min-w-[640px] border-collapse text-sm">
                  <thead>
                    <tr className="border-y border-border bg-surface-2/60 text-left text-[11px] uppercase tracking-wide text-text-faint">
                      <th className="px-5 py-2.5 font-semibold sm:px-6">Player</th>
                      <th className="px-3 py-2.5 text-right font-semibold">Line</th>
                      {bookNames.map((b) => (
                        <th key={b} className="px-3 py-2.5 text-right font-semibold">
                          <span
                            className="inline-flex items-center gap-1.5"
                            style={{ color: bookStyle(b, isDark).color }}
                          >
                            <span
                              aria-hidden="true"
                              className="inline-block h-2 w-2 rounded-sm"
                              style={{ background: bookStyle(b, isDark).color }}
                            />
                            {b}
                          </span>
                        </th>
                      ))}
                      <th className="px-5 py-2.5 sm:px-6" />
                    </tr>
                  </thead>
                  <tbody>
                    {board.data.entries.map((entry) => (
                      <BoardRow
                        key={entry.player}
                        entry={entry}
                        bookNames={bookNames}
                        isDark={isDark}
                        onOpen={() => openPlayer(entry)}
                      />
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 px-5 py-4 text-[11px] text-text-faint sm:px-6">
                <span>
                  Prices are American odds (over / under). "Line" is the median across books.
                </span>
                <OddsFreshness
                  fetchedAt={board.data.fetched_at}
                  requestsRemaining={board.data.requests_remaining}
                />
              </div>
            </Card>
          )}

          <p className="mt-6 text-xs leading-relaxed text-text-faint">
            Lines are shown for information only and may be stale or unavailable. GridEdge does not
            recommend bets, calculate edges, or rank these lines by value — any decision, and all
            of the risk, is yours.
          </p>
        </>
      )}
    </div>
  )
}

function BoardRow({
  entry,
  bookNames,
  isDark,
  onOpen,
}: {
  entry: OddsBoardEntry
  bookNames: string[]
  isDark: boolean
  onOpen: () => void
}) {
  const byBook = new Map<string, BookLine>(entry.books.map((b) => [b.book, b]))

  return (
    <tr
      className="cursor-pointer border-b border-border/60 transition-colors last:border-0 hover:bg-surface-2/70"
      onClick={onOpen}
      tabIndex={0}
      role="button"
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen()
        }
      }}
    >
      <td className="px-5 py-3 font-semibold text-text sm:px-6">{entry.player}</td>
      <td className="px-3 py-3 text-right tabular font-semibold text-text">
        {entry.consensus_line ?? '—'}
      </td>
      {bookNames.map((name) => {
        const b = byBook.get(name)
        return (
          <td key={name} className="px-3 py-3 text-right tabular text-xs text-text-muted">
            {b ? (
              <>
                <span
                  className="block font-semibold"
                  style={{ color: bookStyle(name, isDark).color }}
                >
                  {b.line ?? '—'}
                </span>
                <span className="block text-[11px]">
                  {formatPrice(b.over_price)} / {formatPrice(b.under_price)}
                </span>
              </>
            ) : (
              '—'
            )}
          </td>
        )
      })}
      <td className="px-5 py-3 text-right sm:px-6">
        <span className="inline-flex items-center gap-1 whitespace-nowrap text-xs font-semibold text-accent-soft">
          Analyze
          <ArrowRightIcon className="h-3.5 w-3.5" />
        </span>
      </td>
    </tr>
  )
}
