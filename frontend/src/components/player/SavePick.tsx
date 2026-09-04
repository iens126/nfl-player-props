import { useMemo, useState } from 'react'
import { BookmarkIcon, CheckCircleIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { Link } from 'react-router-dom'
import type { OddsResponse, ProjectionResponse, ScheduleGame } from '../../api/types'
import { statLabel } from '../../lib/statLabels'
import {
  DEFAULT_PRICE, impliedProbability, profitFor, savePick, type PickSide,
} from '../../lib/picks'

/**
 * Save the line on screen to the tracker, with a virtual stake.
 *
 * The price is captured now rather than looked up later: lines move, and a
 * pick has to be settled at the number that was actually on offer when it was
 * taken. It prefills from the books when odds are loaded, and falls back to
 * -110, the standard price on a player prop.
 *
 * Coins are imaginary. Nothing here is purchasable and nothing cashes out.
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
  available: number
  /** Lets the page re-read the bankroll after coins are committed. */
  onSaved?: () => void
}) {
  const bookPrice = useMemo(() => {
    const book = odds?.books?.find((b) => b.over_price !== null || b.under_price !== null)
    return book ?? null
  }, [odds])

  const [side, setSide] = useState<PickSide>(
    projection.prob_over >= projection.prob_under ? 'over' : 'under',
  )
  const [stake, setStake] = useState('100')
  const [priceInput, setPriceInput] = useState('')
  const [saved, setSaved] = useState(false)

  // Whichever side is selected, prefer that side's posted price.
  const suggestedPrice = side === 'over'
    ? bookPrice?.over_price ?? null
    : bookPrice?.under_price ?? null
  const price = priceInput.trim() === ''
    ? suggestedPrice ?? DEFAULT_PRICE
    : Number(priceInput)

  const stakeValue = Number(stake)
  const stakeValid = Number.isFinite(stakeValue) && stakeValue > 0 && stakeValue <= available
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

  function onSave() {
    if (!stakeValid || !priceValid) return
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
      savedAt: Date.now(),
    } as never)
    setSaved(true)
    onSaved?.()
  }

  if (saved) {
    return (
      <div className="rounded-2xl border border-over/40 bg-over/5 p-5">
        <div className="flex items-center gap-2">
          <CheckCircleIcon className="h-5 w-5 text-over" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-over">Pick saved</h3>
        </div>
        <p className="mt-2 text-sm text-text-muted">
          {projection.player} {side} {projection.line} {statLabel(projection.stat)} —{' '}
          <span className="tabular font-semibold text-text">{stakeValue.toLocaleString()}</span> coins
          to win <span className="tabular font-semibold text-text">{Math.round(toWin).toLocaleString()}</span>.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Link
            to="/picks"
            className="inline-flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-semibold text-accent-soft transition-colors hover:bg-accent/15"
          >
            View my picks
          </Link>
          <button
            type="button"
            onClick={() => setSaved(false)}
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
          <BookmarkIcon className="h-4 w-4" />
          Track this pick
        </h3>
        <span className="text-xs text-text-faint">
          {available.toLocaleString()} coins available
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

      <div className="mt-3 grid grid-cols-2 gap-2">
        <label className="block">
          <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-text-faint">
            Stake (coins)
          </span>
          <input
            type="number"
            min="1"
            step="10"
            value={stake}
            onChange={(e) => setStake(e.target.value)}
            className="w-full rounded-xl border border-border bg-surface-2 px-3 py-2 text-sm tabular text-text outline-none focus:border-accent"
          />
        </label>
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
      </div>

      <div className="mt-3 flex flex-wrap items-baseline justify-between gap-2 rounded-xl bg-surface-2 px-3 py-2 text-xs">
        <span className="text-text-muted">
          To win <span className="tabular font-bold text-text">{Math.round(toWin).toLocaleString()}</span> coins
        </span>
        {implied !== null && (
          <span className="text-text-faint">
            book implies {(implied * 100).toFixed(1)}% · model {(modelProb * 100).toFixed(1)}%
          </span>
        )}
      </div>

      {!stakeValid && stake.trim() !== '' && (
        <p className="mt-2 text-xs text-under">
          {stakeValue > available
            ? `You only have ${available.toLocaleString()} coins available.`
            : 'Enter a stake above zero.'}
        </p>
      )}

      <button
        type="button"
        onClick={onSave}
        disabled={!stakeValid || !priceValid}
        className="mt-3 w-full rounded-xl bg-accent px-3 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Save pick
      </button>
      <p className="mt-2 text-[11px] leading-relaxed text-text-faint">
        Coins are imaginary and stay in this browser — there's no account, nothing
        to buy, and nothing to cash out. The price is stored as it is now, so the
        pick settles at the number you took.
      </p>
    </div>
  )
}
