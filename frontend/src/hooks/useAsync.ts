import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/types'

interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: string | null
}

/**
 * Runs `fn` whenever `deps` change. If `enabled` is false, skips the call
 * and leaves data null (used to defer requests until prerequisite
 * selections, like a player name, are available).
 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[], enabled = true): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ data: null, loading: enabled, error: null })
  const requestId = useRef(0)

  useEffect(() => {
    if (!enabled) {
      setState({ data: null, loading: false, error: null })
      return
    }
    const id = ++requestId.current
    setState((s) => ({ ...s, loading: true, error: null }))
    fn()
      .then((data) => {
        if (requestId.current === id) setState({ data, loading: false, error: null })
      })
      .catch((err) => {
        if (requestId.current === id) {
          const message = err instanceof ApiError ? err.message : 'Something went wrong. Please try again.'
          setState({ data: null, loading: false, error: message })
        }
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return state
}
