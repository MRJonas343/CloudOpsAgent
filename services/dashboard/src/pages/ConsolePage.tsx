/**
 * `/console` — the simulated application's status, and the chaos console.
 *
 * This slice renders the read-only half: the app's health and key metrics,
 * polled, so an injected fault is visible as a degraded metric snapshot. The
 * chaos controls themselves (fault injection, the pending-injection state, and
 * honest `403`/`404` surfacing) belong to the console slice and are shown here
 * as a labelled placeholder rather than as buttons that do nothing.
 */

import { useEffect } from 'react'

import { getAppHealth, getAppMetrics } from '../api/client'
import { Badge } from '../components/Badges'
import { ErrorNote, Panel } from '../components/Panel'
import { useApi } from '../hooks/useApi'
import { formatNumber, formatPercent } from '../lib/format'

/** The app has no push channel for metrics, so the panel polls. */
const POLL_INTERVAL_MS = 5000

export function ConsolePage() {
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
  const appStatus = health.data?.status ?? null

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
            <HealthBadge status={appStatus} reachable={health.data !== null} />
            {snapshot?.status && snapshot.status !== 'ok' && (
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

      <Panel step={2} title="Chaos console" hint="not in this slice">
        <div className="space-y-3">
          <p className="text-slate-300">
            Fault injection arrives with the console slice. The controls will call the simulated
            app&rsquo;s existing simulation routes through this same origin, and this page will show
            the injected mode until the agent detects it.
          </p>
          <ul className="list-disc space-y-1 pl-5 text-slate-400">
            <li>
              Inject a <span className="font-mono text-slate-300">traffic_spike</span> or an{' '}
              <span className="font-mono text-slate-300">unhealthy_application</span> fault, and
              reset the app afterwards.
            </li>
            <li>
              Show a pending-injection state until the agent reports the incident, so an operator
              can see the fault was accepted before it is detected.
            </li>
            <li>
              Surface a refused injection honestly — a <span className="font-mono">403</span> when
              the simulation controls are disabled, a{' '}
              <span className="font-mono">404</span> for an unknown mode — with no fabricated
              incident.
            </li>
            <li>Wire the empty-state &ldquo;Generate demo incident&rdquo; call to action to the same trigger.</li>
          </ul>
          <p className="text-xs text-slate-500">
            Nothing on this page injects a fault yet; the status above is read-only.
          </p>
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
