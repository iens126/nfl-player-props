import { useMemo, useState } from 'react'
import { BookmarkIcon, CheckCircleIcon, LockClosedIcon, TrophyIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { Link } from 'react-router-dom'
import type { OddsResponse, ProjectionResponse, ScheduleGame } from '../../api/types'
import { statLabel } from '../../lib/statLabels'
import {
  DEFAULT_PRICE, impliedProbability, profitFor, savePick, type PickSide,
} from '../../lib/picks'
import { accountsEnabled } from '../../lib/supabase'
import { submitPick, useAccountPicks, useProfile } from '../../lib/account'

/**
 * Save the line on screen, either privately or for the leaderboard.
 *
 * The two modes look almost identical and are not the same thing at all.
 *
 * Privately, the user names their own price. That is a feature: it costs
 * nobody anything, and it lets someone track a number they got at a book this
 * app doesn't cover.
 *
 * On the leaderboard, the user names nothing. The price comes back from
 * /api/picks/create, which reads it off the live board, because a price the
 * client chose is a ranking nobody can trust — "over 0.5 receiving yards at
 * +2000" would win every week. The same response supplies the kickoff the pick
 * has to beat. So in ranked mode there is no price field, and the panel reports
 * the price that was actually taken once the pick is in.
 *
 * Coins are imaginary in both modes. Nothing is purchasable and nothing cashes out.
 */
export function SavePick({
  projection,
  odds,
  team,
  schedule,
  available,
  onSaved,
}: {
  projection: ProjectionResponse
  odds: OddsResponse | null
  team: string
  schedule: ScheduleGame[] | null
  /** Coins free to stake in the private tracker. */
  available: number
  /** Lets the page re-read the bankroll after coins are committed. */
  onSaved?: () => void
}) {
  const { profile } = useProfile()
  const account = useAccountPicks()

  // Ranked whenever there's an account to rank. Someone signed in but not yet
  // named can't make a ranked pick, so they keep the private tracker until they
  // finish setting up rather than losing the ability to save anything.
  const ranked = accountsEnabled && Boolean(profile)
  const spendable = ranked ? account.summary.available : available

  const bookPrice = useMemo(() => {
    const book = odds?.books?.find((b) => b.over_price !== null || b.under_price !== null)
    return book ?? null
  }, [odds])

  const [side, setSide] = useState<PickSide>(
    projection.prob_over >= projection.prob_under ? 'over' : 'under',
  )
  // Null until the user types, so the default follows the mode. The profile
  // arrives a moment after first render, and a stake initialised to the
  // private tracker's 100 would then be the whole of a 100-coin bankroll.
  const [typedStake, setTypedStake] = useState<string | null>(null)
  const stake = typedStake ?? (ranked ? '10' : '100')
  const [priceInput, setPriceInput] = useState('')
  const [saved, setSaved] = useState<{ price: number; book: string | null } | null>(null)
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)

  // Whichever side is selected, prefer that side's posted price.
  const suggestedPrice = side === 'over'
    ? bookPrice?.over_price ?? null
    : bookPrice?.under_price ?? null
  const price = priceInput.trim() === ''
    ? suggestedPrice ?? DEFAULT_PRICE
    : Number(priceInput)

  const stakeValue = Number(stake)
  const stakeValid = Number.isFinite(stakeValue) && stakeValue >= 1 && stakeValue <= spendable
  const priceValid = Number.isFinite(price) && price !== 0 && Math.abs(price) >= 100

  const toWin = stakeValid && priceValid ? profitFor(stakeValue, price) : 0
  const implied = priceValid ? impliedProbability(price) : null
  const modelProb = side === 'over' ? projection.prob_over : projection.prob_under

  // The scheduled game this pick belongs to, so it can be settled against the
  // right week and told apart from "the player didn't suit up".
  const game = useMemo(() => {
    if (!schedule) return null
    return schedule.find(
      (g) => (g.home_team === team && g.away_team === projection.opponent)
        || (g.away_team === team && g.home_team === projection.opponent),
    ) ?? null
  }, [schedule, team, projection.opponent])

  async function onSave() {
    if (!stakeValid || (!ranked && !priceValid)) return
    setProblem(null)

    if (!ranked) {
      savePick({
        player: projection.player,
        team,
        opponent: projection.opponent,
        stat: projection.stat,
        line: projection.line,
        side,
        stake: stakeValue,
        price,
        book: bookPrice?.book ?? null,
        season: new Date().getFullYear(),
        week: game?.week ?? null,
        gameday: game?.gameday ?? null,
        modelProb,
      })
      setSaved({ price, book: bookPrice?.book ?? null })
      onSaved?.()
      return
    }

    setBusy(true)
    try {
      const result = await submitPick({
        player: projection.player,
        team,
        opponent: projection.opponent,
        stat: projection.stat,
        side,
        line: projection.line,
        stake: stakeValue,
        model_prob: modelProb,
      })
      setSaved({ price: result.price, book: result.book })
      account.refresh()
      onSaved?.()
    } catch (error) {
      setProblem(error instanceof Error ? error.message : 'The pick could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  if (saved) {
    return (
      <div className="rounded-2xl border border-over/40 bg-over/5 p-5">
        <div className="flex items-center gap-2">
          <CheckCircleIcon className="h-5 w-5 text-over" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-over">
            {ranked ? 'Ranked pick placed' : 'Pick saved'}
          </h3>
        </div>
        <p className="mt-2 text-sm text-text-muted">
          {projection.player} {side} {projection.line} {statLabel(projection.stat)} —{' '}
          <span className="tabular font-semibold text-text">{stakeValue.toLocaleString()}</span> coins
          at <span className="tabular font-semibold text-text">
            {saved.price > 0 ? `+${saved.price}` : saved.price}
          </span>
          {saved.book ? ` (${saved.book})` : ''}, to win{' '}
          <span className="tabular font-semibold text-text">
            {Math.round(profitFor(stakeValue, saved.price)).toLocaleString()}
          </span>.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Link
            to="/picks"
            className="inline-flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-semibold text-accent-soft transition-colors hover:bg-accent/15"
          >
            View my picks
          </Link>
          {ranked && (
            <Link
              to="/leaderboard"
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-text-muted transition-colors hover:bg-surface-2"
            >
              Leaderboard
            </Link>
          )}
          <button
            type="button"
            onClick={() => { setSaved(null); setProblem(null) }}
            className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-text-muted transition-colors hover:bg-surface-2"
          >
            Save another
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-border bg-surface p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-text-muted">
          {ranked ? <TrophyIcon className="h-4 w-4" /> : <BookmarkIcon className="h-4 w-4" />}
          {ranked ? 'Make a ranked pick' : 'Track this pick'}
        </h3>
        <span className="text-xs text-text-faint">
          {Math.round(spendable).toLocaleString()} coins available
        </span>
      </div>

      <p className="mt-2 text-xs text-text-muted">
        {projection.player} · {statLabel(projection.stat)}{' '}
        <span className="tabular font-semibold text-text">{projection.line}</span> vs {projection.opponent}
        {game?.week ? ` · Week ${game.week}` : ''}
      </p>

      <div className="mt-3 grid grid-cols-2 gap-2">
        {(['over', 'under'] as PickSide[]).map((s) => {
          const prob = s === 'over' ? projection.prob_over : projection.prob_under
          return (
            <button
              key={s}
              type="button"
              onClick={() => setSide(s)}
              className={clsx(
                'rounded-xl border px-3 py-2 text-left transition-colors',
                side === s
                  ? s === 'over' ? 'border-over/50 bg-over/10' : 'border-under/50 bg-under/10'
                  : 'border-border bg-surface-2 hover:bg-surface-3',
              )}
            >
              <span className={clsx(
                'block text-[11px] font-bold uppercase tracking-wide',
                s === 'over' ? 'text-over' : 'text-under',
              )}>
                {s}
              </span>
              <span className="tabular text-sm font-semibold text-text">
                {(prob * 100).toFixed(0)}% model
              </span>
            </button>
          )
        })}
      </div>

      <div className={clsx('mt-3 grid gap-2', ranked ? 'grid-cols-1' : 'grid-cols-2')}>
        <label className="block">
          <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-text-faint">
            Stake (coins)
          </span>
          <input
            type="number"
            min="1"
            step={ranked ? '1' : '10'}
            value={stake}
            onChange={(e) => setTypedStake(e.target.value)}
            className="w-full rounded-xl border border-border bg-surface-2 px-3 py-2 text-sm tabular text-text outline-none focus:border-accent"
          />
        </label>
        {!ranked && (
          <label className="block">
            <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-text-faint">
              Price
            </span>
            <input
              type="number"
              step="5"
              placeholder={String(suggestedPrice ?? DEFAULT_PRICE)}
              value={priceInput}
              onChange={(e) => setPriceInput(e.target.value)}
              className="w-full rounded-xl border border-border bg-surface-2 px-3 py-2 text-sm tabular text-text outline-none focus:border-accent"
            />
          </label>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-baseline justify-between gap-2 rounded-xl bg-surface-2 px-3 py-2 text-xs">
        <span className="text-text-muted">
          {ranked ? 'To win about ' : 'To win '}
          <span className="tabular font-bold text-text">{Math.round(toWin).toLocaleString()}</span> coins
        </span>
        {implied !== null && (
          <span className="text-text-faint">
            book implies {(implied * 100).toFixed(1)}% · model {(modelProb * 100).toFixed(1)}%
          </span>
        )}
      </div>

      {!stakeValid && stake.trim() !== '' && (
        <p className="mt-2 text-xs text-under">
          {stakeValue > spendable
            ? `You only have ${Math.round(spendable).toLocaleString()} coins available.`
            : 'The smallest stake is 1 coin.'}
        </p>
      )}

      {problem && <p className="mt-2 text-xs text-under">{problem}</p>}

      <button
        type="button"
        onClick={() => void onSave()}
        disabled={busy || !stakeValid || (!ranked && !priceValid)}
        className="mt-3 w-full rounded-xl bg-accent px-3 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {busy ? 'Checking the board…' : ranked ? 'Place ranked pick' : 'Save pick'}
      </button>

      {ranked ? (
        <p className="mt-2 flex items-start gap-1.5 text-[11px] leading-relaxed text-text-faint">
          <LockClosedIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            The price is taken from the live board when you place this, not from
            here, and the pick locks at kickoff. It settles automatically once the
            game is played and counts towards the leaderboard.
          </span>
        </p>
      ) : (
        <p className="mt-2 text-[11px] leading-relaxed text-text-faint">
          Coins are imaginary and stay in this browser — nothing to buy and nothing
          to cash out. The price is stored as it is now, so the pick settles at the
          number you took.
        </p>
      )}
    </div>
  )
}
