import { useState } from 'react'
import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react'
import { UserCircleIcon, ClipboardIcon, CheckIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { accountsEnabled } from '../../lib/supabase'
import {
  recoverAccount, registerAccount, signIn, signOut, useProfile, useSession,
} from '../../lib/account'

/**
 * Sign in with a username and a password. Nothing else is asked for.
 *
 * There is no email field here, and that is the design rather than an omission:
 * the account record is a username and a date, so there is nothing to type
 * that the leaderboard doesn't already show. See core/accounts.py.
 *
 * The cost of collecting no contact address is that a forgotten password
 * cannot be mailed back, so registration ends on a recovery code the user is
 * told, in as many words, to save now. That panel is rendered from `Menu`
 * rather than from the form that produced it, because signing up signs you in,
 * and the form beneath it unmounts the moment that happens.
 *
 * Renders nothing at all when accounts aren't configured, so a deployment
 * without a Supabase project shows no dead sign-in button.
 */
export function AccountMenu() {
  if (!accountsEnabled) return null
  return <Menu />
}

type Mode = 'signin' | 'register' | 'recover'

function Menu() {
  const { session, ready } = useSession()
  const { profile, loading, refresh } = useProfile()
  const [code, setCode] = useState<{ value: string | null; note?: string } | null>(null)

  if (!ready) return <div className="h-8 w-8" aria-hidden />

  const label = profile?.username ?? (session ? 'Account' : 'Sign in')

  return (
    <Popover className="relative">
      <PopoverButton className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm font-medium text-text-muted transition-colors hover:bg-surface-2 hover:text-text">
        <UserCircleIcon className="h-5 w-5" />
        <span className="hidden max-w-[9rem] truncate sm:inline">{label}</span>
      </PopoverButton>

      <PopoverPanel className="absolute right-0 z-50 mt-2 w-80 rounded-2xl border border-border bg-surface p-4 shadow-xl">
        {code ? (
          <ShowRecoveryCode code={code.value} note={code.note} onDone={() => setCode(null)} />
        ) : session && profile ? (
          <SignedIn username={profile.username} />
        ) : (
          <Auth
            onRegistered={(value) => { setCode({ value }); refresh() }}
            onRecovered={(value, note) => { setCode({ value, note }); refresh() }}
            onSignedIn={refresh}
            busy={loading}
          />
        )}
      </PopoverPanel>
    </Popover>
  )
}

// ---------------------------------------------------------------------------
// Forms
// ---------------------------------------------------------------------------

const TABS: { key: Mode; label: string }[] = [
  { key: 'signin', label: 'Sign in' },
  { key: 'register', label: 'Create account' },
]

function Auth({ onRegistered, onRecovered, onSignedIn, busy }: {
  onRegistered: (code: string) => void
  onRecovered: (code: string | null, note?: string) => void
  onSignedIn: () => void
  busy: boolean
}) {
  const [mode, setMode] = useState<Mode>('signin')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [recoveryCode, setRecoveryCode] = useState('')
  const [working, setWorking] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const ready = username.trim().length >= 3 && password.length >= 10
    && (mode !== 'recover' || recoveryCode.trim().length > 0)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setWorking(true)
    setError(null)
    try {
      if (mode === 'register') {
        const { recoveryCode: issued } = await registerAccount(username.trim(), password)
        onRegistered(issued)
      } else if (mode === 'recover') {
        const result = await recoverAccount(username.trim(), recoveryCode.trim(), password)
        onRecovered(result.recoveryCode, result.message)
      } else {
        await signIn(username.trim(), password)
        onSignedIn()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Try again.')
    } finally {
      setWorking(false)
    }
  }

  return (
    <>
      {mode !== 'recover' && (
        <div className="mb-3 flex rounded-xl bg-surface-2 p-1">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => { setMode(tab.key); setError(null) }}
              className={clsx(
                'flex-1 rounded-lg px-2 py-1.5 text-xs font-semibold transition-colors',
                mode === tab.key ? 'bg-surface text-text shadow-sm' : 'text-text-muted hover:text-text',
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}

      {mode === 'recover' && <h3 className="text-sm font-bold text-text">Use a recovery code</h3>}

      <p className="mt-1 text-xs leading-relaxed text-text-muted">
        {mode === 'register' && (
          <>A username and a password — no email, no phone number. You get 100 imaginary
          coins and a place on the leaderboard.</>
        )}
        {mode === 'signin' && (
          <>Picks without an account still work — they just stay in this browser.</>
        )}
        {mode === 'recover' && (
          <>Enter the code you saved when you signed up, and the password you'd like instead.</>
        )}
      </p>

      <form onSubmit={submit} className="mt-3 space-y-2">
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          maxLength={20}
          autoComplete="username"
          placeholder="username"
          aria-label="Username"
          className="w-full rounded-xl border border-border bg-surface-2 px-3 py-2 text-sm text-text outline-none focus:border-accent"
        />

        {mode === 'recover' && (
          <input
            value={recoveryCode}
            onChange={(e) => setRecoveryCode(e.target.value)}
            placeholder="XXXXX-XXXXX-XXXXX-XXXXX"
            aria-label="Recovery code"
            className="w-full rounded-xl border border-border bg-surface-2 px-3 py-2 font-mono text-xs uppercase tracking-wider text-text outline-none focus:border-accent"
          />
        )}

        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
          placeholder={mode === 'signin' ? 'password' : 'new password'}
          aria-label={mode === 'signin' ? 'Password' : 'New password'}
          className="w-full rounded-xl border border-border bg-surface-2 px-3 py-2 text-sm text-text outline-none focus:border-accent"
        />

        <button
          type="submit"
          disabled={!ready || working || busy}
          className="w-full rounded-xl bg-accent px-3 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          {working
            ? 'Working…'
            : mode === 'register' ? 'Create account'
            : mode === 'recover' ? 'Set new password'
            : 'Sign in'}
        </button>
      </form>

      {mode !== 'signin' && (
        <p className="mt-2 text-[11px] leading-relaxed text-text-faint">
          3–20 characters: letters, numbers and underscores. Passwords are at least
          10 characters.
        </p>
      )}

      {error && <p className="mt-2 text-xs text-under">{error}</p>}

      <button
        type="button"
        onClick={() => { setMode(mode === 'recover' ? 'signin' : 'recover'); setError(null) }}
        className="mt-3 w-full text-center text-[11px] text-text-muted underline-offset-2 hover:text-text hover:underline"
      >
        {mode === 'recover' ? 'Back to sign in' : 'Forgotten your password?'}
      </button>
    </>
  )
}

// ---------------------------------------------------------------------------
// The recovery code
// ---------------------------------------------------------------------------

/**
 * The one time this code is ever shown. Only its hash reaches the database, so
 * it cannot be looked up again by the user, by support, or by whoever runs the
 * server — which is worth saying on the panel rather than burying in a doc.
 */
function ShowRecoveryCode({ code, note, onDone }: {
  code: string | null
  note?: string
  onDone: () => void
}) {
  const [copied, setCopied] = useState(false)
  const [saved, setSaved] = useState(false)

  if (!code) {
    return (
      <>
        <h3 className="text-sm font-bold text-warn">Password changed</h3>
        <p className="mt-1.5 text-xs leading-relaxed text-text-muted">
          {note ?? 'Your password was changed, but a new recovery code could not be issued.'}
        </p>
        <button
          type="button"
          onClick={onDone}
          className="mt-3 w-full rounded-xl bg-accent px-3 py-2 text-sm font-semibold text-white"
        >
          Done
        </button>
      </>
    )
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(code!)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard access can be refused; the code is on screen to be copied by hand.
    }
  }

  return (
    <>
      <h3 className="text-sm font-bold text-text">Save your recovery code</h3>
      <p className="mt-1.5 text-xs leading-relaxed text-text-muted">
        Because we never asked for your email, this is the <strong className="text-text">only</strong> way
        back into your account if you forget your password. It is not shown again, and
        nobody can look it up for you.
      </p>

      <div className="mt-3 rounded-xl border border-border bg-surface-2 px-3 py-2.5 text-center font-mono text-sm tracking-wider text-text">
        {code}
      </div>

      <button
        type="button"
        onClick={copy}
        className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-xl border border-border px-3 py-2 text-xs font-semibold text-text-muted transition-colors hover:bg-surface-2 hover:text-text"
      >
        {copied ? <CheckIcon className="h-4 w-4" /> : <ClipboardIcon className="h-4 w-4" />}
        {copied ? 'Copied' : 'Copy code'}
      </button>

      <label className="mt-3 flex cursor-pointer items-start gap-2 text-xs text-text-muted">
        <input
          type="checkbox"
          checked={saved}
          onChange={(e) => setSaved(e.target.checked)}
          className="mt-0.5 h-3.5 w-3.5 rounded border-border accent-[var(--color-accent,#6366f1)]"
        />
        I have saved this code somewhere safe.
      </label>

      <button
        type="button"
        disabled={!saved}
        onClick={onDone}
        className="mt-3 w-full rounded-xl bg-accent px-3 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
      >
        Continue
      </button>
    </>
  )
}

function SignedIn({ username }: { username: string }) {
  return (
    <>
      <h3 className="text-sm font-bold text-text">{username}</h3>
      <p className="mt-1 text-xs leading-relaxed text-text-muted">
        Ranked picks are settled after each game and count towards the leaderboard.
        The only thing stored about you is this name.
      </p>
      <button
        type="button"
        onClick={() => void signOut()}
        className="mt-3 w-full rounded-xl border border-border px-3 py-2 text-sm font-semibold text-text-muted transition-colors hover:bg-surface-2 hover:text-text"
      >
        Sign out
      </button>
    </>
  )
}
