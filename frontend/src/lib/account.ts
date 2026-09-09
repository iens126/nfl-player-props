import { useCallback, useState, useSyncExternalStore } from 'react'
import type { Session } from '@supabase/supabase-js'
import { ApiError } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { accountsEnabled, client, supabase } from './supabase'
import { summarise, type BankrollSummary, type PickSide, type PickStatus } from './picks'

/**
 * Accounts, ranked picks and the leaderboard.
 *
 * The division of labour here is the whole design, so it is worth stating
 * plainly: **this file never writes a pick.** It reads them, and it posts a
 * request to /api/picks/create, which is the only thing anywhere with
 * permission to insert one. The database grants the browser no INSERT on
 * picks at all.
 *
 * That is not defensive habit, it is the point. A ranked pick carries a line
 * and a price, and if the browser supplied those, "over 0.5 receiving yards at
 * +2000" would win every week and own the ROI board forever. The server reads
 * both off the live sportsbook board instead, along with the kickoff it must
 * beat. See api/picks/create.py and supabase/schema.sql.
 *
 * Balances are never stored either. A bankroll is 100 coins plus the profit on
 * everything settled, recomputed from the picks themselves every time it is
 * shown — so regrading a game can never leave a total that disagrees with the
 * tickets behind it.
 */

/** Matches app.starting_bankroll() in supabase/schema.sql. */
export const ACCOUNT_BANKROLL = 100

/** Matches app.roi_qualifying_stake(). Kept here only for the empty-state copy. */
export const ROI_QUALIFYING_STAKE = 25

// Same origin on Vercel; set only when a local frontend talks to a deployed API.
const API_BASE = (import.meta.env.VITE_ODDS_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export interface Settlement {
  status: Exclude<PickStatus, 'pending'>
  actual: number | null
  week: number | null
  profit: number
  graded_at: string
}

export interface AccountPick {
  id: string
  user_id: string
  player: string
  team: string
  opponent: string
  stat: string
  line: number
  side: PickSide
  stake: number
  price: number
  book: string | null
  event_id: string | null
  season: number
  kickoff: string
  model_prob: number | null
  created_at: string
  /** Null until the nightly job has settled it. */
  settlement: Settlement | null
}

export interface LeaderboardRow {
  user_id: string
  username: string
  hits: number
  misses: number
  voids: number
  pending: number
  profit: number
  staked: number
  balance: number
  /** Null until enough has been staked for a return to mean anything. */
  roi: number | null
  roi_qualified: boolean
  roi_threshold: number
}

export interface Profile {
  id: string
  username: string
  created_at: string
}

/**
 * Extends ApiError so useAsync surfaces the real message rather than its
 * generic fallback — "That username is taken" is worth reading.
 */
export class AccountError extends ApiError {
  constructor(message: string, status = 0) {
    super(status, message)
  }
}

// ---------------------------------------------------------------------------
// Session
//
// One module-level store rather than a provider, matching lib/theme.ts: every
// component that cares about who is signed in reads the same value, and the
// nav bar and the picks page can't disagree about it.
// ---------------------------------------------------------------------------

let session: Session | null = null
let ready = !accountsEnabled
const listeners = new Set<() => void>()

function emit() {
  listeners.forEach((fn) => fn())
}

if (supabase) {
  void supabase.auth.getSession().then(({ data }) => {
    session = data.session
    ready = true
    emit()
  })
  supabase.auth.onAuthStateChange((_event, next) => {
    session = next
    ready = true
    emit()
  })
}

function subscribe(fn: () => void) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

/** The current session, and whether we've finished finding out. */
export function useSession(): { session: Session | null; ready: boolean } {
  const snapshot = useSyncExternalStore(
    subscribe,
    () => session,
    () => null,
  )
  const settled = useSyncExternalStore(subscribe, () => ready, () => true)
  return { session: snapshot, ready: settled }
}

// ---------------------------------------------------------------------------
// Registering, signing in, recovering
//
// A username and a password. That is the whole of what GridEdge asks a person
// for, and `profiles` — (id, username, created_at) — is the whole of what it
// keeps about them. No email address, no phone number, no OAuth profile
// arriving with a real name and an avatar attached.
//
// Supabase's auth service will not hold a password account without an
// identifier, and takes only an email or a phone, so one is synthesised from
// the username against a domain that RFC 2606 guarantees can never resolve.
// core/accounts.py explains the reasoning; this file only has to build the
// same string, because signing in happens before any server of ours is called.
//
// What follows from having no contact address is that a forgotten password
// cannot be mailed back, so registration hands out a recovery code instead —
// once, and never again.
// ---------------------------------------------------------------------------

/** Must match EMAIL_DOMAIN in core/accounts.py. Never routes anywhere. */
export const ACCOUNT_EMAIL_DOMAIN = 'users.gridedge.invalid'

/** Lowercased, so the auth service's uniqueness agrees with profiles_username_lower_idx. */
export function syntheticEmail(username: string): string {
  return `${username.trim().toLowerCase()}@${ACCOUNT_EMAIL_DOMAIN}`
}

/** POST JSON to one of our own functions, turning any failure into an AccountError. */
async function post<T>(path: string, payload: unknown, token?: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
    })
  } catch {
    throw new AccountError('Could not reach the server. Check your connection and try again.')
  }

  const parsed = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new AccountError(parsed?.message ?? `Something went wrong (${response.status}).`, response.status)
  }
  return parsed as T
}

export interface Registration {
  profile: Profile
  /** Shown once. Not stored anywhere we can read it back from. */
  recoveryCode: string
}

/**
 * Create the account, then sign straight into it.
 *
 * The two steps are separate because only the server may create a profile —
 * the browser has no INSERT grant on it (see supabase/schema.sql) — but the
 * user should not have to type their password twice to get through the door.
 */
export async function registerAccount(username: string, password: string): Promise<Registration> {
  const created = await post<{ profile: Profile; recovery_code: string }>(
    '/api/account/register', { username, password },
  )
  await signIn(username, password)
  return { profile: created.profile, recoveryCode: created.recovery_code }
}

export async function signIn(username: string, password: string): Promise<void> {
  const { error } = await client().auth.signInWithPassword({
    email: syntheticEmail(username),
    password,
  })
  if (error) {
    // The provider talks about an email address the user never typed.
    throw new AccountError(
      /invalid login credentials/i.test(error.message)
        ? 'That username and password do not match.'
        : error.message,
    )
  }
}

export interface Recovery {
  /** Null in the rare case the password changed but a new code could not be issued. */
  recoveryCode: string | null
  message?: string
}

/** Set a new password using the code issued at registration, then sign in. */
export async function recoverAccount(
  username: string, recoveryCode: string, password: string,
): Promise<Recovery> {
  const result = await post<{ recovery_code: string | null; message?: string }>(
    '/api/account/recover', { username, recovery_code: recoveryCode, password },
  )
  await signIn(username, password)
  return { recoveryCode: result.recovery_code, message: result.message }
}

export async function signOut(): Promise<void> {
  await client().auth.signOut()
}

// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------

export async function fetchProfile(userId: string): Promise<Profile | null> {
  const { data, error } = await client()
    .from('profiles').select('id, username, created_at').eq('id', userId).maybeSingle()
  if (error) throw new AccountError(error.message)
  return data as Profile | null
}

/** The signed-in user's profile. Created with the account, so a signed-in
 * user always has one — null here means the lookup hasn't landed yet. */
export function useProfile(): { profile: Profile | null; loading: boolean; refresh: () => void } {
  const { session: current, ready } = useSession()
  const [nonce, setNonce] = useState(0)

  const state = useAsync(
    () => (current ? fetchProfile(current.user.id) : Promise.resolve(null)),
    [current?.user.id, nonce],
    accountsEnabled && ready,
  )

  return {
    profile: state.data,
    loading: state.loading,
    refresh: useCallback(() => setNonce((n) => n + 1), []),
  }
}

// ---------------------------------------------------------------------------
// Picks
// ---------------------------------------------------------------------------

const PICK_COLUMNS =
  'id, user_id, player, team, opponent, stat, line, side, stake, price, book, ' +
  'event_id, season, kickoff, model_prob, created_at, ' +
  'settlement:settlements(status, actual, week, profit, graded_at)'

/**
 * supabase-js can't type an embedded relationship without generated database
 * types, and generating them would put a build step between this repo and a
 * schema it doesn't own. The shape is asserted in normalise() instead.
 */
function rows(data: unknown): Record<string, unknown>[] {
  return Array.isArray(data) ? (data as Record<string, unknown>[]) : []
}

/** Postgres numerics arrive as strings over PostgREST; the UI wants numbers. */
function normalise(row: Record<string, unknown>): AccountPick {
  const raw = row.settlement as Settlement | Settlement[] | null
  const settlement = Array.isArray(raw) ? (raw[0] ?? null) : raw
  return {
    ...(row as unknown as AccountPick),
    line: Number(row.line),
    stake: Number(row.stake),
    price: Number(row.price),
    model_prob: row.model_prob === null ? null : Number(row.model_prob),
    settlement: settlement
      ? {
          ...settlement,
          actual: settlement.actual === null ? null : Number(settlement.actual),
          profit: Number(settlement.profit),
        }
      : null,
  }
}

export async function fetchMyPicks(userId: string): Promise<AccountPick[]> {
  const { data, error } = await client()
    .from('picks').select(PICK_COLUMNS).eq('user_id', userId).order('created_at', { ascending: false })
  if (error) throw new AccountError(error.message)
  return rows(data).map(normalise)
}

/** Another user's picks — visible only once their games have kicked off. */
export async function fetchUserPicks(userId: string): Promise<AccountPick[]> {
  const { data, error } = await client()
    .from('picks').select(PICK_COLUMNS).eq('user_id', userId).order('kickoff', { ascending: false })
  if (error) throw new AccountError(error.message)
  return rows(data).map(normalise)
}

export async function fetchLeaderboard(): Promise<LeaderboardRow[]> {
  const { data, error } = await client().from('leaderboard').select('*')
  if (error) throw new AccountError(error.message)
  return rows(data).map((row) => ({
    ...(row as unknown as LeaderboardRow),
    profit: Number(row.profit),
    staked: Number(row.staked),
    balance: Number(row.balance),
    roi: row.roi === null ? null : Number(row.roi),
    roi_threshold: Number(row.roi_threshold),
  }))
}

export interface PickRequest {
  player: string
  team: string
  opponent: string
  stat: string
  side: PickSide
  line: number
  stake: number
  model_prob: number | null
}

/**
 * Ask the server to take a pick.
 *
 * Note what isn't in PickRequest: a price. The server reads it off the board,
 * because a price the client chose is a leaderboard nobody can trust. What
 * comes back includes the price actually taken, which is usually the first
 * thing the user wants to see.
 */
export async function submitPick(request: PickRequest): Promise<{ pick: AccountPick; price: number; book: string | null }> {
  const { data } = await client().auth.getSession()
  const token = data.session?.access_token
  if (!token) throw new AccountError('Sign in to make a ranked pick.')

  const body = await post<{ pick: Record<string, unknown> }>('/api/picks/create', request, token)
  const pick = normalise(body.pick)
  return { pick, price: pick.price, book: pick.book }
}

// ---------------------------------------------------------------------------
// Summarising
// ---------------------------------------------------------------------------

/** Record and bankroll for one account, on the same arithmetic as local picks. */
export function summariseAccount(picks: AccountPick[]): BankrollSummary {
  return summarise(
    picks.map((p) => ({
      status: (p.settlement?.status ?? 'pending') as PickStatus,
      stake: p.stake,
      profit: p.settlement?.profit ?? 0,
    })),
    ACCOUNT_BANKROLL,
  )
}

/**
 * The signed-in account's picks, bankroll and record.
 *
 * `available` is what SavePick offers to stake: the balance less everything
 * already riding on games that haven't finished. The server checks it again
 * inside the transaction that writes the pick — this figure is for the user,
 * not for the rules.
 */
export function useAccountPicks(): {
  picks: AccountPick[] | null
  summary: BankrollSummary
  loading: boolean
  error: string | null
  refresh: () => void
} {
  const { session: current, ready } = useSession()
  const [nonce, setNonce] = useState(0)

  const state = useAsync(
    () => (current ? fetchMyPicks(current.user.id) : Promise.resolve([])),
    [current?.user.id, nonce],
    accountsEnabled && ready && Boolean(current),
  )

  return {
    picks: state.data,
    summary: summariseAccount(state.data ?? []),
    loading: state.loading,
    error: state.error,
    refresh: useCallback(() => setNonce((n) => n + 1), []),
  }
}
