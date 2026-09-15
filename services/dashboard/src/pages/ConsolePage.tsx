/**
 * `/console` — the simulated application's status, and the chaos console.
 *
 * The read half is the app's health and key metrics, polled, so an injected
 * fault is visible as a degraded snapshot. The control half injects exactly one
 * real fault and can reset it, both through the app's own `/simulate` routes
 * over the same origin.
 *
 * Nothing on this page creates an incident. It shows the fault it injected and
 * then waits for the agent to report what it actually detects — see `useChaos`.
 */

import { useEffect, useState } from 'react'

import { getAppHealth, getAppMetrics } from '../api/client'
import type { FaultMode } from '../api/types'
import { Badge } from '../components/Badges'
import { ChaosErrorNote, InjectionStatus } from '../components/InjectionStatus'
import { ErrorNote, Panel } from '../components/Panel'
import { useApi } from '../hooks/useApi'
import type { ChaosController } from '../hooks/useChaos'
import { useCountdown } from '../hooks/useCountdown'
import { formatCountdown, formatNumber, formatPercent, humanize } from '../lib/format'

/** The app has no push channel for metrics, so the panel polls. */
const POLL_INTERVAL_MS = 5000

/** Both modes have a detector in the agent; other incident types have none. */
const FAULT_MODES: readonly FaultMode[] = ['traffic_spike', 'unhealthy_application']

/** Duration presets in seconds; the app clamps requests to its own 1..300 bound. */
const DURATIONS = [15, 30, 60, 120] as const
const DEFAULT_DURATION_SECONDS = 30

const INPUT =
  'rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-200 transition hover:border-slate-500 focus:outline-none focus:ring-1 focus:ring-sky-500 disabled:cursor-not-allowed disabled:opacity-50'

const ACTION = `${INPUT} border-sky-600 bg-sky-600/20 font-medium text-sky-100 hover:border-sky-400 hover:bg-sky-600/30`

export function ConsolePage({ chaos }: { chaos: ChaosController }) {
  const [duration, setDuration] = useState<number>(DEFAULT_DURATION_SECONDS)
  const [resetting, setResetting] = useState(false)

  const health = useApi(getAppHealth, [])
  const metrics = useApi(getAppMetrics, [])
  const reloadHealth = health.reload
  const reloadMetrics = metrics.reload

  useEffect(() => {
    const timer = window.setInterval(() => {
      reloadHealth()
      reloadMetrics()
    }, POLL_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [reloadHealth, reloadMetrics])

  const snapshot = metrics.data
  const appHealth = health.data?.status ?? null

  const { simulation, simulationError, simulationLoading } = chaos
  const remaining = useCountdown(simulation?.remaining_seconds)
  // One fault at a time: while an injection is in flight or waiting on the
  // agent, the controls rest rather than swapping the fault underneath it.
  const busy = chaos.phase === 'injecting' || chaos.phase === 'pending'

  const handleReset = async () => {
    setResetting(true)
    try {
      await chaos.reset()
    } finally {
      setResetting(false)
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-slate-100">Application console</h1>
        <p className="text-sm text-slate-500">
          Live view of the simulated application, refreshed every {POLL_INTERVAL_MS / 1000}s
          {metrics.loading && metrics.data !== null && <span className="ml-2 text-sky-400">updating…</span>}
        </p>
      </div>

      {health.error && <ErrorNote status={health.error.status} message={health.error.message} />}
      {metrics.error && <ErrorNote status={metrics.error.status} message={metrics.error.message} />}

      <Panel
        step={1}
        title="Application status"
        hint={health.data ? `service ${health.data.service}` : undefined}
      >
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs tracking-wide text-slate-500 uppercase">Health</span>
            <HealthBadge status={appHealth} reachable={health.data !== null} />
            {snapshot && snapshot.status !== 'ok' && (
              <span className="text-xs text-slate-500">metrics report {snapshot.status}</span>
            )}
          </div>

          {snapshot ? (
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-6">
              <Metric label="CPU" value={`${formatNumber(snapshot.cpu_percent)}%`} />
              <Metric label="Memory" value={`${formatNumber(snapshot.memory_percent)}%`} />
              <Metric label="p95 latency" value={`${formatNumber(snapshot.latency_ms_p95)} ms`} />
              <Metric label="Requests / s" value={formatNumber(snapshot.requests_per_second)} />
              <Metric label="Error rate" value={formatPercent(snapshot.error_rate)} />
              <Metric label="Replicas" value={String(snapshot.replicas)} />
            </dl>
          ) : (
            <p className="text-sm text-slate-500">
              {metrics.loading ? 'Loading metrics…' : 'No metrics available.'}
            </p>
          )}

          {snapshot && (
            <p className="text-xs text-slate-600">
              {snapshot.request_count} requests / {snapshot.error_count} errors since the app
              started.
            </p>
          )}
        </div>
      </Panel>

      <Panel step={2} title="Active fault" hint="GET /simulate/status">
        <div className="space-y-3">
          {simulationError && (
            <ErrorNote status={simulationError.status} message={simulationError.message} />
          )}

          {!simulationError && simulation === null && (
            <p className="text-sm text-slate-500">
              {simulationLoading ? 'Reading the simulation status…' : 'No simulation status available.'}
            </p>
          )}

          {simulation !== null && simulation.mode === null && (
            <p className="text-sm text-slate-400">
              No active fault. The app is reporting baseline health and metrics.
            </p>
          )}

          {simulation !== null && simulation.mode !== null && (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="amber">{humanize(simulation.mode)}</Badge>
                <span className="font-mono text-slate-100">
                  {remaining === null ? '—' : formatCountdown(remaining)}
                </span>
                <span className="text-xs text-slate-500">until it auto-expires</span>
              </div>
              {/*
                Only the duration and the countdown are shown. `started_at` and
                `expires_at` are the app's `time.monotonic()` values, not wall
                time, so rendering them as clock times would invent a timestamp.
              */}
              <p className="text-xs text-slate-500">
                Injected for {simulation.duration_seconds ?? '—'}s. The app clears the fault on its
                own when the countdown above reaches zero.
              </p>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <button type="button" className={INPUT} onClick={() => void handleReset()} disabled={resetting}>
              {resetting ? 'Resetting…' : 'Reset simulation'}
            </button>
            <span className="text-xs text-slate-500">
              Clears the active fault with <span className="font-mono">POST /simulate/reset</span>.
            </span>
          </div>
        </div>
      </Panel>

      <Panel step={3} title="Chaos console" hint="POST /simulate/{mode}">
        <div className="space-y-3">
          <p className="text-slate-300">
            Inject a real fault into the simulated application. The Monitor detects it from the
            degraded health and metrics and opens the incident. This page never posts an incident:
            whatever appears in the live list was found by the agent, not created by the UI.
          </p>

          <div className="flex flex-wrap items-end gap-2">
            {FAULT_MODES.map((fault) => (
              <button
                key={fault}
                type="button"
                className={ACTION}
                onClick={() => void chaos.inject(fault, duration)}
                disabled={busy}
              >
                {chaos.phase === 'injecting' && chaos.mode === fault
                  ? 'Injecting…'
                  : humanize(fault)}
              </button>
            ))}

            <label className="flex flex-col gap-1 text-xs text-slate-500">
              Duration
              <select
                className={INPUT}
                value={duration}
                onChange={(event) => setDuration(Number(event.target.value))}
                disabled={busy}
              >
                {DURATIONS.map((seconds) => (
                  <option key={seconds} value={seconds}>
                    {seconds}s
                  </option>
                ))}
              </select>
            </label>
          </div>

          <InjectionStatus chaos={chaos} />

          {chaos.error && <ChaosErrorNote error={chaos.error} />}
        </div>
      </Panel>
    </div>
  )
}

function HealthBadge({ status, reachable }: { status: string | null; reachable: boolean }) {
  if (!reachable) return <Badge tone="slate">unreachable</Badge>
  if (status === 'ok') return <Badge tone="emerald">ok</Badge>
  if (status === 'unhealthy') return <Badge tone="rose">unhealthy</Badge>
  return <Badge tone="amber">{status ?? 'unknown'}</Badge>
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs tracking-wide text-slate-500 uppercase">{label}</dt>
      <dd className="font-mono text-lg text-slate-100">{value}</dd>
    </div>
  )
}
