/**
 * Tick the approval deadline down on the client.
 *
 * The server owns the deadline and re-reports `remaining_seconds` on every read.
 * Anchoring a local deadline to that number — rather than to the absolute
 * timestamp — keeps the countdown honest even if the browser clock and the
 * container clock disagree, and re-anchoring on each refresh stops drift.
 */

import { useEffect, useState } from 'react'

export function useCountdown(remainingSeconds: number | null | undefined): number | null {
  const [deadline, setDeadline] = useState<number | null>(null)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (remainingSeconds === null || remainingSeconds === undefined) {
      setDeadline(null)
      return
    }
    setDeadline(Date.now() + remainingSeconds * 1000)
    setNow(Date.now())
  }, [remainingSeconds])

  useEffect(() => {
    if (deadline === null) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [deadline])

  if (deadline === null) return null
  return Math.max(0, Math.ceil((deadline - now) / 1000))
}
