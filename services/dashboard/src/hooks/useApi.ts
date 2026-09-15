/**
 * A tiny read hook: load once, reload when the caller's keys change, and reload
 * on demand. Every page is a read view over REST plus the event stream, so this
 * is the whole "data layer" — no store, no cache, no state library.
 *
 * A reload keeps the previous data on screen (`loading` is a flag, not a wipe),
 * because a live list that blanks on every event would be worse than one that
 * lags a beat.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from '../api/client'

export interface ApiFailure {
  /** HTTP status when the failure came from the API; `null` for a transport error. */
  status: number | null
  message: string
}

export interface ApiState<T> {
  data: T | null
  error: ApiFailure | null
  loading: boolean
  reload: () => void
}

/** Normalise any thrown value into the `{status, message}` the UI renders. */
export function describeError(error: unknown): ApiFailure {
  if (error instanceof ApiError) {
    return { status: error.status, message: error.message }
  }
  if (error instanceof Error) {
    return { status: null, message: error.message }
  }
  return { status: null, message: 'Unexpected error' }
}

export function useApi<T>(load: () => Promise<T>, keys: readonly unknown[]): ApiState<T> {
  const loadRef = useRef(load)
  const [version, setVersion] = useState(0)
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiFailure | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadRef.current = load
  })

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    loadRef
      .current()
      .then((result) => {
        if (cancelled) return
        setData(result)
        setError(null)
      })
      .catch((failure: unknown) => {
        if (cancelled) return
        setError(describeError(failure))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // The caller's keys plus the manual-reload counter; React compares the
    // elements, so a fresh array literal each render is fine.
  }, [...keys, version])

  const reload = useCallback(() => setVersion((current) => current + 1), [])

  return { data, error, loading, reload }
}
