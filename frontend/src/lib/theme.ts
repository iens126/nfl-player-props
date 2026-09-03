import { useCallback, useSyncExternalStore } from 'react'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'gridedge-theme'

/**
 * Shared theme state.
 *
 * This was originally a plain `useState` inside the hook, which gave every
 * caller its own independent copy: toggling in the nav bar flipped the
 * document attribute, so CSS-token colours changed, but no other component
 * re-rendered. Anything computing a colour in JavaScript from the theme — the
 * team colours on the performance chart, the sportsbook swatches — silently
 * kept its old values until a reload.
 *
 * One module-level value with subscribers fixes that without adding a provider
 * to the tree.
 */

function systemTheme(): Theme {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

/** Whatever the pre-paint script in index.html already applied. */
function initialTheme(): Theme {
  const attr = document.documentElement.getAttribute('data-theme')
  if (attr === 'dark' || attr === 'light') return attr
  return systemTheme()
}

let current: Theme = typeof document === 'undefined' ? 'light' : initialTheme()
const listeners = new Set<() => void>()

function emit() {
  listeners.forEach((listener) => listener())
}

function apply(theme: Theme, remember: boolean) {
  current = theme
  document.documentElement.setAttribute('data-theme', theme)
  if (remember) {
    try {
      localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      // Private browsing or blocked storage: the theme still applies for this
      // session, it just won't be remembered.
    }
  }
  emit()
}

export function setTheme(theme: Theme) {
  apply(theme, true)
}

export function toggleTheme() {
  apply(current === 'dark' ? 'light' : 'dark', true)
}

// Follow the OS while the user hasn't made an explicit choice.
if (typeof window !== 'undefined' && window.matchMedia) {
  const query = window.matchMedia('(prefers-color-scheme: dark)')
  query.addEventListener('change', (event) => {
    let stored: string | null = null
    try {
      stored = localStorage.getItem(STORAGE_KEY)
    } catch {
      return
    }
    if (!stored) apply(event.matches ? 'dark' : 'light', false)
  })
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function getSnapshot(): Theme {
  return current
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, getSnapshot, () => 'light' as Theme)
  const toggle = useCallback(() => toggleTheme(), [])
  return { theme, toggle }
}
