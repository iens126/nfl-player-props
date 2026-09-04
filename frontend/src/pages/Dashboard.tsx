import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ArrowsRightLeftIcon, CalendarDaysIcon } from '@heroicons/react/24/outline'
import { api, ApiError } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { SearchSelect, type SelectItem } from '../components/selectors/SearchSelect'
import { Card, SectionHeading } from '../components/common/Card'
import { Skeleton, SkeletonCard } from '../components/common/Skeleton'
import { ErrorState } from '../components/common/ErrorState'
import { PlayerHeader } from '../components/player/PlayerHeader'
import { StatCard } from '../components/player/StatCard'
import { OverUnderPanel } from '../components/player/OverUnderPanel'
import { PropForm } from '../components/player/PropForm'
import { PerformanceChart, type ChartRange } from '../components/player/PerformanceChart'
import { GameLogTable } from '../components/player/GameLogTable'
import { StabilityPanel } from '../components/player/StabilityPanel'
import { DefenseMatchup } from '../components/player/DefenseMatchup'
import { DefenseRoles } from '../components/player/DefenseRoles'
import { Collapsible } from '../components/common/Collapsible'
import { HowItWorks } from '../components/layout/HowItWorks'
import { ModelConsensus } from '../components/player/ModelConsensus'
import { HitRatePanel } from '../components/player/HitRatePanel'
import { OddsList } from '../components/player/OddsList'
import { LineExplorer } from '../components/player/LineExplorer'
import { ModelInfoPanel } from '../components/player/ModelInfoPanel'
import { statLabel } from '../lib/statLabels'
import { matchupColors } from '../lib/teamColors'
import { useTheme } from '../lib/theme'
import type { AlternatesResponse, ModelKey, OddsResponse, ProjectionResponse } from '../api/types'

const PASS_TYPE_STATS = new Set([
  'passing_yards', 'passing_tds', 'completions', 'attempts', 'passing_interceptions',
  'receiving_yards', 'receiving_tds', 'targets', 'receptions',
])
const RUSH_TYPE_STATS = new Set(['carries', 'rushing_yards', 'rushing_tds'])

// How many games PlayerSummary.recent_averages covers. Mirrors SIM_WINDOW in
// core/monte_carlo_sim.py, which is what the backend averages over.
const RECENT_WINDOW_GAMES = 3

// The prop most people are looking for first, per position, in preference order.
const PREFERRED_STAT: Record<string, string[]> = {
  QB: ['passing_yards', 'passing_tds', 'completions'],
  RB: ['rushing_yards', 'carries', 'receiving_yards'],
  WR: ['receiving_yards', 'receptions', 'targets'],
  TE: ['receiving_yards', 'receptions', 'targets'],
}

export default function Dashboard() {
  // The odds board links here with a player/stat/line already chosen, so the
  // initial state honours those params before falling back to the defaults.
  const [searchParams, setSearchParams] = useSearchParams()

  const [position, setPosition] = useState<string | null>(null)
  const [team, setTeam] = useState<string | null>(null)
  const [player, setPlayer] = useState<string | null>(() => searchParams.get('player'))
  const [opponent, setOpponent] = useState<string | null>(() => searchParams.get('opponent'))
  const [stat, setStat] = useState<string | null>(() => searchParams.get('stat'))
  const [lineInput, setLineInput] = useState(() => searchParams.get('line') ?? '')
  const [range, setRange] = useState<ChartRange>('season')
  const [model, setModel] = useState<ModelKey>(
    () => (searchParams.get('model') as ModelKey | null) ?? 'ensemble',
  )
  const { theme } = useTheme()

  // Keep the URL describing what's on screen, so a view can be bookmarked,
  // reloaded, or sent to someone else and come back the same. Written with
  // `replace` so typing a line doesn't fill the back button with history.
  useEffect(() => {
    const params = new URLSearchParams()
    if (player) params.set('player', player)
    if (stat) params.set('stat', stat)
    if (lineInput) params.set('line', lineInput)
    if (opponent) params.set('opponent', opponent)
    if (model !== 'ensemble') params.set('model', model)
    setSearchParams(params, { replace: true })
    // setSearchParams isn't referentially stable, so depending on it would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [player, stat, lineInput, opponent, model])

  const teams = useAsync(() => api.teams(), [])
  const positions = useAsync(() => api.positions(), [])
  const schedule = useAsync(() => api.scheduleUpcoming(21), [])
  const models = useAsync(() => api.models(stat ?? undefined), [stat])

  const players = useAsync(
    () => api.players({ team: team ?? undefined, position: position ?? undefined, limit: 1000 }),
    [team, position],
  )

  const summary = useAsync(() => api.playerSummary(player!), [player], !!player)
  const gameLog = useAsync(() => api.playerGameLog(player!), [player], !!player)
  const defense = useAsync(() => api.defense(opponent!), [opponent], !!opponent)
  const chart = useAsync(
    () => api.playerChart(player!, stat!, opponent!, range),
    [player, stat, opponent, range],
    !!player && !!stat && !!opponent,
  )

  // Reset the player when team/position filters no longer include it.
  useEffect(() => {
    if (player && players.data && players.data.length > 0 && !players.data.some((p) => p.name === player)) {
      setPlayer(null)
    }
  }, [players.data, player])

  // Default to the prop people actually look up for that position (a QB's
  // passing yards, a back's rushing yards) rather than whichever stat happens
  // to come first in the list.
  useEffect(() => {
    if (summary.data && (!stat || !summary.data.available_stats.includes(stat))) {
      const available = summary.data.available_stats
      const preferred = PREFERRED_STAT[summary.data.position] ?? []
      setStat(preferred.find((s) => available.includes(s)) ?? available[0] ?? null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [summary.data])

  // Auto-suggest the player's next scheduled opponent, once, when a player is picked.
  useEffect(() => {
    if (!summary.data || opponent || !schedule.data) return
    const playerTeam = summary.data.team
    const game = schedule.data.find((g) => g.home_team === playerTeam || g.away_team === playerTeam)
    if (game) setOpponent(game.home_team === playerTeam ? game.away_team : game.home_team)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [summary.data, schedule.data])

  const canSwap = !!summary.data && !!opponent

  function swapMatchup() {
    if (!summary.data || !opponent) return
    const offenseTeam = summary.data.team
    setTeam(opponent)
    setOpponent(offenseTeam)
    setPlayer(null)
  }

  const line = useMemo(() => {
    const n = parseFloat(lineInput)
    return Number.isFinite(n) && n > 0 ? n : null
  }, [lineInput])

  const [projection, setProjection] = useState<{ data: ProjectionResponse | null; loading: boolean; error: string | null }>({
    data: null,
    loading: false,
    error: null,
  })

  useEffect(() => {
    if (!player || !opponent || !stat || line === null) {
      setProjection({ data: null, loading: false, error: null })
      return
    }
    setProjection((p) => ({ ...p, loading: true, error: null }))
    const handle = setTimeout(() => {
      api
        .projection({ player, opponent, stat, line, model })
        .then((data) => setProjection({ data, loading: false, error: null }))
        .catch((err) => {
          const message = err instanceof ApiError ? err.message : 'Could not calculate a projection.'
          setProjection({ data: null, loading: false, error: message })
        })
    }, 350)
    return () => clearTimeout(handle)
  }, [player, opponent, stat, line, model])

  // Odds are fetched per player/stat/matchup only - each call costs provider
  // credits, so nothing here refetches on a line change.
  const [odds, setOdds] = useState<{ data: OddsResponse | null; loading: boolean }>({
    data: null,
    loading: false,
  })

  useEffect(() => {
    const team = summary.data?.team
    if (!player || !opponent || !stat || !team) {
      setOdds({ data: null, loading: false })
      return
    }
    let cancelled = false
    setOdds({ data: null, loading: true })
    api
      .odds({ player, team, opponent, stat })
      .then((data) => !cancelled && setOdds({ data, loading: false }))
      .catch(() => !cancelled && setOdds({ data: null, loading: false }))
    return () => {
      cancelled = true
    }
  }, [player, opponent, stat, summary.data?.team])

  // The alternate-line ladder costs an extra API credit, so it is only
  // fetched when the user asks for it, and reset whenever the matchup changes.
  const [alternates, setAlternates] = useState<{
    data: AlternatesResponse | null
    loading: boolean
    requested: boolean
    probabilities: Record<number, number>
  }>({ data: null, loading: false, requested: false, probabilities: {} })

  useEffect(() => {
    setAlternates({ data: null, loading: false, requested: false, probabilities: {} })
  }, [player, opponent, stat])

  // The ladder is priced once when it loads, so changing the model afterwards
  // would leave every rung describing the previous one. Re-price in place.
  useEffect(() => {
    const rungs = alternates.data?.lines
    if (!player || !opponent || !stat || !rungs?.length) return
    let cancelled = false
    api
      .probabilitiesFor({ player, opponent, stat, model, lines: rungs.map((l) => l.line) })
      .then((probabilities) => {
        if (!cancelled) setAlternates((a) => ({ ...a, probabilities }))
      })
      .catch(() => { /* the rungs simply show no model reading */ })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model, alternates.data])

  async function loadAlternates() {
    const eventId = odds.data?.event_id
    // The button is disabled while odds are pending, so reaching here without
    // an event id means the books genuinely have no game for this matchup.
    if (!player || !stat || !eventId) {
      setAlternates({
        data: {
          status: 'no_event',
          message: 'The books have no game listed for this matchup yet.',
          player, stat, lines: [], fetched_at: null, requests_remaining: null,
        },
        loading: false, requested: true, probabilities: {},
      })
      return
    }

    setAlternates((a) => ({ ...a, loading: true, requested: true }))
    try {
      const data = await api.oddsAlternates(eventId, stat, player)
      // Price every rung locally in one pass so the slider doesn't refetch.
      let probabilities: Record<number, number> = {}
      if (data.status === 'ok' && opponent && data.lines.length) {
        probabilities = await api.probabilitiesFor({
          player, opponent, stat, model, lines: data.lines.map((l) => l.line),
        })
      }
      setAlternates({ data, loading: false, requested: true, probabilities })
    } catch {
      setAlternates({
        data: {
          status: 'error', message: 'Could not load the alternate lines.',
          player, stat, lines: [], fetched_at: null, requests_remaining: null,
        },
        loading: false, requested: true, probabilities: {},
      })
    }
  }

  const activeModelInfo = (models.data ?? []).find((m) => m.key === model) ?? null

  const positionItems: SelectItem[] = (positions.data ?? []).map((p) => ({ value: p, label: p }))
  const teamItems: SelectItem[] = (teams.data ?? []).map((t) => ({ value: t.abbr, label: `${t.abbr} — ${t.name}`, accent: t.color }))
  const playerItems: SelectItem[] = (players.data ?? []).map((p) => ({ value: p.name, label: p.name, sublabel: `${p.team} · ${p.position}` }))
  const opponentTeam = teams.data?.find((t) => t.abbr === opponent) ?? null

  const opponentItems: SelectItem[] = (teams.data ?? [])
    .filter((t) => t.abbr !== summary.data?.team)
    .map((t) => ({ value: t.abbr, label: `${t.abbr} — ${t.name}`, accent: t.color }))

  const chartColors = matchupColors(summary.data?.team, opponent, teams.data, theme === 'dark')

  const showPassing = summary.data?.available_stats.some((s) => PASS_TYPE_STATS.has(s)) ?? false
  const showRushing = summary.data?.available_stats.some((s) => RUSH_TYPE_STATS.has(s)) ?? false

  return (
    <div className="mx-auto max-w-7xl px-4 pb-24 pt-8 sm:px-6 lg:px-8 2xl:max-w-[1680px]">
      <div className="mb-5">
        <h1 className="text-2xl font-extrabold tracking-tight text-text sm:text-3xl">Player Prop Analysis</h1>
        {/* The standfirst explains the tool, which stops being useful the
            moment there's a player on screen - and it was costing vertical
            space the analysis wanted. */}
        {!player && (
          <p className="mt-1.5 max-w-2xl text-sm text-text-muted">
            Pick a player and matchup to see recent form, opponent defense, and a modelled
            over/under projection for any prop line.
          </p>
        )}
      </div>

      <HowItWorks startCollapsed={!!player} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="order-2 space-y-6 lg:order-1">
          <Card>
            <SectionHeading
              title="Select Matchup"
              action={
                <button
                  type="button"
                  onClick={swapMatchup}
                  disabled={!canSwap}
                  title="Swap offense and defense"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-text-muted transition-colors hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <ArrowsRightLeftIcon className="h-3.5 w-3.5" />
                  Swap
                </button>
              }
            />
            <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
              <SearchSelect label="Position" placeholder="Any position" items={positionItems} value={position} onChange={setPosition} />
              <SearchSelect label="Team" placeholder="Any team" items={teamItems} value={team} onChange={setTeam} />
              <SearchSelect
                label="Player"
                placeholder={players.loading ? 'Loading players…' : 'Search players…'}
                items={playerItems}
                value={player}
                onChange={setPlayer}
                disabled={players.loading}
              />
              <SearchSelect
                label="Opponent"
                placeholder="Select opponent"
                items={opponentItems}
                value={opponent}
                onChange={setOpponent}
                disabled={!summary.data}
                disabledHint="Pick a player first"
              />
            </div>
          </Card>

          {!player && <EmptyState />}

          {player && summary.loading && <LoadingBlock />}
          {player && summary.error && <ErrorState message={summary.error} />}

          {player && summary.data && (
            <>
              <Card>
                <PlayerHeader summary={summary.data} opponent={opponentTeam} />
              </Card>

              {/* Prop analysis sits directly under the player, because every
                  number below it is specific to the stat and line chosen here.
                  The chart runs alongside on wide screens so the projection and
                  the form behind it are visible together rather than a scroll
                  apart. */}
              <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                <Card>
                  <SectionHeading title="Prop Analysis" subtitle="Enter a line to see the model's over/under read" />
                  <PropForm
                    availableStats={summary.data.available_stats}
                    stat={stat}
                    onStatChange={setStat}
                    line={lineInput}
                    onLineChange={setLineInput}
                    models={models.data ?? []}
                    model={model}
                    onModelChange={setModel}
                  />

                  <div className="mt-4 grid grid-cols-3 gap-2.5">
                    <StatCard
                      label="Projection"
                      value={projection.data ? projection.data.projection.toFixed(1) : '—'}
                      sublabel={stat ? statLabel(stat) : undefined}
                      tone="accent"
                    />
                    <StatCard
                      label="Prob. Over"
                      value={projection.data ? `${(projection.data.prob_over * 100).toFixed(0)}%` : '—'}
                      sublabel={line !== null ? `over ${line}` : undefined}
                      tone="over"
                    />
                    <StatCard
                      label="Prob. Under"
                      value={projection.data ? `${(projection.data.prob_under * 100).toFixed(0)}%` : '—'}
                      sublabel={line !== null ? `under ${line}` : undefined}
                      tone="under"
                    />
                    <StatCard
                      label="Recent Avg"
                      value={stat && summary.data.recent_averages[stat] !== undefined ? summary.data.recent_averages[stat].toFixed(1) : '—'}
                      sublabel={`Last ${RECENT_WINDOW_GAMES} games`}
                    />
                    <StatCard
                      label="Season Avg"
                      value={stat && summary.data.season_averages[stat] !== undefined ? summary.data.season_averages[stat].toFixed(1) : '—'}
                      sublabel={`${summary.data.games_played} games`}
                    />
                    <StatCard
                      label="Stability"
                      value={summary.data.stability.find((s) => s.stat === stat)?.rating ?? '—'}
                      sublabel="week to week"
                      tone="neutral"
                    />
                  </div>

                  <div className="mt-4">
                    {!opponent && <p className="text-sm text-text-faint">Select an opponent to run a projection.</p>}
                    {opponent && line === null && <p className="text-sm text-text-faint">Enter a prop line above to see the model's projection.</p>}
                    {opponent && line !== null && projection.loading && <ProjectionSkeleton />}
                    {opponent && line !== null && projection.error && <ErrorState message={projection.error} />}
                    {opponent && line !== null && !projection.loading && projection.data && (
                      <OverUnderPanel result={projection.data} />
                    )}
                  </div>
                </Card>

                {stat && opponent ? (
                  <Card>
                    <SectionHeading
                      title="Performance Chart"
                      subtitle={
                        range === 'career'
                          ? `${summary.data.team} ${statLabel(stat)} across their career, against what ${opponent} allows`
                          : `${summary.data.team} ${statLabel(stat)} by week, against what ${opponent} allows`
                      }
                    />
                    {chart.loading && <Skeleton className="h-72 w-full" />}
                    {chart.error && <ErrorState message={chart.error} />}
                    {chart.data && (
                      <PerformanceChart
                        chart={chart.data}
                        range={range}
                        onRangeChange={setRange}
                        line={line}
                        opponentAbbr={opponent}
                        playerAbbr={summary.data.team}
                        colors={chartColors}
                      />
                    )}
                  </Card>
                ) : (
                  <Card className="flex items-center justify-center py-12 text-center">
                    <p className="max-w-xs text-sm text-text-faint">
                      Pick an opponent to chart this player against what that defense allows.
                    </p>
                  </Card>
                )}
              </div>

              {/* Sits directly under the chart it contextualises: the chart shows
                  what this defense allowed week to week, and this is the season
                  summary and league rank behind those bars. */}
              {opponent && (
                <Card>
                  <SectionHeading
                    title="Defensive Matchup"
                    subtitle={`What ${opponent} allows, with league ranks from this season's team data`}
                  />
                  {defense.loading && (
                    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                      <SkeletonCard />
                      <SkeletonCard />
                    </div>
                  )}
                  {defense.error && <ErrorState message={defense.error} />}
                  {defense.data && (
                    <>
                      <DefenseMatchup defense={defense.data} showPassing={showPassing} showRushing={showRushing} />
                      <DefenseRoles team={opponent} roles={defense.data.roles ?? []} />
                    </>
                  )}
                </Card>
              )}

              {/* Supporting reads. Three across on a wide screen so the whole
                  picture fits a browser window instead of a long scroll. */}
              {opponent && line !== null && !projection.loading && projection.data && (
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
                  <ModelConsensus result={projection.data} />
                  <HitRatePanel result={projection.data} />
                  <ModelInfoPanel info={activeModelInfo} />
                </div>
              )}

              {/* The book panels don't depend on the projection, so they sit
                  outside its loading gate. Inside it, every keystroke in the
                  line field unmounted them: the odds flickered out and back,
                  and the line explorer lost its slider position on each edit. */}
              {opponent && (
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <OddsList odds={odds.data} loading={odds.loading} />
                  <LineExplorer
                    alternates={alternates.data}
                    loading={alternates.loading}
                    oddsPending={odds.loading}
                    requested={alternates.requested}
                    onRequest={loadAlternates}
                    onProbabilityFor={(line) => alternates.probabilities[line] ?? null}
                  />
                </div>
              )}

              <Card>
                <SectionHeading title="Game Log" />
                {gameLog.loading && <Skeleton className="h-64 w-full" />}
                {gameLog.error && <ErrorState message={gameLog.error} />}
                {gameLog.data && <GameLogTable gameLog={gameLog.data} highlightStat={stat} line={line} />}
              </Card>

              <Card>
                <SectionHeading title="Player Stability" subtitle="How consistent this player's production has been" />
                <StabilityPanel stability={summary.data.stability} />
              </Card>

              {projection.data && (
                <Collapsible title="How is this projection calculated?">
                  <ProjectionExplainer result={projection.data} />
                </Collapsible>
              )}
            </>
          )}
        </div>

        <aside className="order-1 space-y-4 lg:order-2 lg:sticky lg:top-20 lg:self-start">
          <Card>
            <SectionHeading title="Upcoming Games" action={<CalendarDaysIcon className="h-4 w-4 text-text-faint" />} />
            {schedule.loading && <Skeleton className="h-40 w-full" />}
            {schedule.error && <ErrorState compact message={schedule.error} />}
            {schedule.data && schedule.data.length === 0 && <p className="text-sm text-text-faint">No games in range.</p>}
            {schedule.data && schedule.data.length > 0 && (
              <ul className="space-y-1.5">
                {schedule.data.slice(0, 12).map((g, i) => (
                  <li key={i}>
                    <button
                      onClick={() => {
                        setTeam(g.home_team)
                        setOpponent(g.away_team)
                      }}
                      className="flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-xs transition-colors hover:bg-surface-2"
                    >
                      <span className="text-text-faint">{formatGameday(g.gameday)}</span>
                      <span className="font-semibold text-text-muted">
                        {g.away_team} <ArrowsRightLeftIcon className="mx-1 inline h-3 w-3" /> {g.home_team}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </aside>
      </div>
    </div>
  )
}

// `gameday` is a plain "YYYY-MM-DD" string with no time/zone. Parsing it with
// `new Date(str)` treats it as UTC midnight, which can render as the previous
// day once formatted in a timezone behind UTC - so build the Date from local
// year/month/day parts instead.
function formatGameday(gameday: string): string {
  const [year, month, day] = gameday.split('-').map(Number)
  const date = new Date(year, month - 1, day)
  return date.toLocaleDateString(undefined, { weekday: 'short', month: 'numeric', day: 'numeric' })
}

function EmptyState() {
  return (
    <Card className="flex flex-col items-center gap-2 py-16 text-center">
      <p className="text-lg font-semibold text-text">Select a player to get started</p>
      <p className="max-w-sm text-sm text-text-faint">
        Filter by position or team, or pick a player directly to see their recent performance and matchup analysis.
      </p>
    </Card>
  )
}

function LoadingBlock() {
  return (
    <div className="space-y-6">
      <Card>
        <div className="flex items-center gap-5">
          <Skeleton className="h-24 w-24 rounded-2xl" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-4 w-64" />
          </div>
        </div>
      </Card>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    </div>
  )
}

function ProjectionSkeleton() {
  return (
    <div className="rounded-2xl border border-border bg-surface p-6">
      <Skeleton className="h-3 w-32 mb-3" />
      <Skeleton className="h-10 w-40 mb-5" />
      <Skeleton className="h-3 w-full mb-5" />
      <div className="grid grid-cols-2 gap-4">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    </div>
  )
}

function ProjectionExplainer({ result }: { result: ProjectionResponse }) {
  return (
    <div className="space-y-3">
      <p>
        The model starts from {result.player}'s last {result.window_games} games of{' '}
        {statLabel(result.stat)}, weighted so recent games count for more — weights halve every
        three games back. That comes to an effective sample of about{' '}
        <span className="tabular font-semibold text-text">{result.effective_games.toFixed(1)}</span>{' '}
        games, with a form average of{' '}
        <span className="tabular font-semibold text-text">{result.form_average.toFixed(1)}</span>.
      </p>
      <p>
        It then fits a distribution whose shape matches how the stat actually behaves —{' '}
        <span className="font-semibold text-text">{result.model_label}</span>. Yardage is modelled
        as continuous, right-skewed, and able to land on zero; counting stats like receptions and
        touchdowns are modelled as discrete events. With few games to go on, the spread is pulled
        toward a league-typical value, so a short history produces a wider, less confident
        projection rather than false precision.
      </p>
      <p>
        Each outcome is shifted by a <span className="font-semibold text-text">matchup weight</span>{' '}
        of{' '}
        <span className="tabular font-semibold text-text">
          {result.weight >= 0 ? '+' : ''}
          {result.weight.toFixed(2)}
        </span>{' '}
        against {result.opponent}. For quarterbacks this is based on the opponent's pass defense
        z-score relative to the league, scaled by the player's own volatility. For skill-position
        players it compares what {result.opponent} allows to players at the same depth-chart rank
        (e.g. a team's WR1) against the league average at that rank — a closer proxy for the
        specific matchup than a defense's blended average across every receiver it has faced.
      </p>
      <p>
        The <span className="font-semibold text-text">projection</span> is the adjusted mean of
        that distribution, and the <span className="font-semibold text-over">over</span>/
        <span className="font-semibold text-under">under</span> probabilities are its exact mass
        above and below your line — computed in closed form rather than sampled, so the same
        inputs always return the same answer. These are statistical estimates from historical
        data, not guarantees.
      </p>
    </div>
  )
}
