/**
 * The injection readout, shared by the empty-state call to action and the chaos
 * console: one honest statement of where an injected fault stands, and one
 * honest statement of a refused injection.
 *
 * Both surfaces show the same state because both drive the same trigger, and an
 * operator who injects a fault from `/` and then opens `/console` should not
 * read two different stories about it.
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import type { ChaosController } from '../hooks/useChaos'
import type { ApiFailure } from '../hooks/useApi'
import { humanize } from '../lib/format'
import { ErrorNote } from './Panel'

/**
 * A refused injection, explained. The status line comes from the app itself
 * (`403` disabled, `404` unknown mode), and the extra note is what turns "403"
 * into an operator-actionable fact.
 */
export function ChaosErrorNote({ error }: { error: ApiFailure }) {
  return (
    <div className="space-y-1 text-left">
      <ErrorNote status={error.status} message={error.message} />
      {error.status === 403 && (
        <p className="text-xs text-rose-200/80">
          The simulated app runs with{' '}
          <span className="font-mono">APP_SIMULATION_ENABLED=false</span>, so it refuses every{' '}
          <span className="font-mono">/simulate</span> route. No fault was injected and no incident
          was created.
        </p>
      )}
    </div>
  )
}

/** Seconds since the fault was accepted; ticks only while something is pending. */
function useElapsedSeconds(since: number | null, active: boolean): number | null {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!active) return
    setNow(Date.now())
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [active])

  if (!active || since === null) return null
  return Math.max(0, Math.round((now - since) / 1000))
}

export function InjectionStatus({ chaos }: { chaos: ChaosController }) {
  const elapsed = useElapsedSeconds(chaos.injectedAt, chaos.phase === 'pending')

  if (chaos.phase === 'pending' && chaos.mode !== null) {
    return (
      <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3.5 py-2.5 text-sm text-amber-100">
        <p className="font-semibold">
          Injection pending — {humanize(chaos.mode)}
          {elapsed !== null && (
            <span className="ml-2 font-normal text-amber-200/80">{elapsed}s elapsed</span>
          )}
        </p>
        <p className="mt-0.5 text-xs text-amber-200/80">
          The app accepted the fault. Detection is asynchronous and may take up to one poll interval
          (~10s); the incident appears only once the agent reports it.
        </p>
      </div>
    )
  }

  if (chaos.phase === 'reported' && chaos.incidentId !== null) {
    return (
      <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3.5 py-2.5 text-sm text-emerald-100">
        <p className="font-semibold">Reported by the agent</p>
        <p className="mt-0.5 text-xs text-emerald-200/80">
          The injected fault was detected and stored as{' '}
          <Link
            to={`/incidents/${encodeURIComponent(chaos.incidentId)}`}
            className="font-mono text-emerald-200 underline hover:text-emerald-100"
          >
            {chaos.incidentId}
          </Link>
          .
        </p>
      </div>
    )
  }

  if (chaos.phase === 'undetected') {
    return (
      <div className="rounded-lg border border-slate-700 bg-slate-900/60 px-3.5 py-2.5 text-sm text-slate-300">
        <p className="font-semibold">No incident reported</p>
        <p className="mt-0.5 text-xs text-slate-400">
          The injected fault ended before the agent reported a new incident. Nothing is fabricated
          here — an incident of this type may already be active, or the monitor did not classify it.
        </p>
      </div>
    )
  }

  return null
}
