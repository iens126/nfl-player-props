import type { ScheduleGame } from '../api/types'

/**
 * Who a team plays next.
 *
 * Used to fill in the opponent as soon as a player is chosen, so the ordinary
 * question — how does this player look in the game they are about to play —
 * takes one selection instead of two.
 *
 * The earliest fixture is found by comparing dates rather than by taking the
 * first match in the array. The bundle's schedule happens to be in date order
 * today, and the caller sorts it as well, but "their next game" silently
 * becoming "whichever of their games this array happened to list first" is not
 * a failure anyone would notice on screen — the page would just quietly
 * describe the wrong defense.
 */
export function nextOpponentFor(
  schedule: ScheduleGame[] | null | undefined,
  team: string | null | undefined,
): string | null {
  if (!schedule || !team) return null

  let soonest: ScheduleGame | null = null
  for (const game of schedule) {
    // A row listing a team against itself is bad data, and returning that team
    // as its own opponent would ask the engine for a matchup that can't exist.
    if (game.home_team === game.away_team) continue
    if (game.home_team !== team && game.away_team !== team) continue
    // gameday is ISO yyyy-mm-dd, so lexical order is chronological order.
    if (!soonest || game.gameday < soonest.gameday) soonest = game
  }

  if (!soonest) return null
  return soonest.home_team === team ? soonest.away_team : soonest.home_team
}

/**
 * Whether the opponent currently on screen belongs to the user or to the app.
 *
 * A player name means that player's opponent was chosen deliberately — by hand,
 * or named in a link — and should survive until the player changes. `'next'`
 * means the choice should carry to whichever player is picked next, which is
 * what the Swap button needs: it sets a defense and then asks for a player to
 * measure against it. `null` means nothing is pinned and the fixture list wins.
 *
 * No real player is named 'next'; player names in this bundle are "First Last".
 */
export type OpponentPin = string | 'next' | null

export interface AutoFill {
  /** What the opponent should be now. */
  opponent: string | null
  /** The pin to carry forward. */
  pin: OpponentPin
}

/**
 * Decide the opponent for the player who has just been selected.
 *
 * This runs on every player change, not just the first. Filling in once and
 * then stopping is the subtler bug of the two: switching players keeps the
 * previous player's defense, and the projection, chart, hit rates and matchup
 * panels all go on to describe a game that is not being played, while looking
 * completely ordinary.
 */
export function autoFillOpponent(input: {
  pin: OpponentPin
  player: string
  team: string
  schedule: ScheduleGame[] | null | undefined
  opponent: string | null
}): AutoFill {
  const { pin, player, team, schedule, opponent } = input

  // Swap just set a defense and cleared the player; this is that player.
  if (pin === 'next') return { opponent, pin: player }

  // The user picked this player's defense themselves. Leave it.
  if (pin === player) return { opponent, pin }

  const next = nextOpponentFor(schedule, team)

  // The pin is dropped, not carried. Whatever opponent ends up selected here
  // was chosen by the fixture list, so it belongs to nobody — and leaving the
  // old name on it means returning to that player later reads their pin as
  // still standing, over an opponent they never picked. Going Lamb (pin MIN)
  // -> Darnold (fills NE) -> Lamb would then keep NE, quietly showing a
  // Cowboy against New England.
  //
  // A bye — or out of season, when nobody has a fixture inside the horizon —
  // leaves whatever is already selected. Clearing it would empty the page in
  // exactly the months when the user has to choose a matchup by hand anyway.
  return { opponent: next ?? opponent, pin: null }
}
