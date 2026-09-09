import { createClient, type SupabaseClient } from '@supabase/supabase-js'

/**
 * The account backend, or nothing at all.
 *
 * Accounts are optional in exactly the way live odds are: without the keys the
 * app is still the app. The leaderboard says so plainly, picks fall back to the
 * private tracker in this browser, and nothing throws. A fork of this repo
 * should not have to sign up for anything to run.
 *
 * Only the anon key ever reaches the browser, and it is not a secret — every
 * table it can touch is behind row-level security, and no table grants INSERT
 * to anybody. Picks are written by one serverless function holding the service
 * key, after it has checked the line against the live board (api/picks/create.py).
 */

const URL = import.meta.env.VITE_SUPABASE_URL as string | undefined
const ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined

export const accountsEnabled = Boolean(URL && ANON_KEY)

export const supabase: SupabaseClient | null = accountsEnabled
  ? createClient(URL!, ANON_KEY!, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    })
  : null

/** Throws rather than returning null, for the paths that already checked. */
export function client(): SupabaseClient {
  if (!supabase) throw new Error('Accounts are not configured on this deployment.')
  return supabase
}
