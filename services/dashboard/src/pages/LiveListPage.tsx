/**
 * `/` — the live incident list.
 *
 * One REST read for the initial list, then one `EventSource` shared through the
 * stream prop: every lifecycle frame (and every reconnect, which is the only
 * time the stream can have missed something) re-reads the list. Nothing here
 * polls and nothing here needs a manual reload; the Refresh button is a
 * convenience, not the mechanism.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'

import { listIncidents } from '../api/client'
import type { IncidentStatus, IncidentType } from '../api/types'
import { SeverityBadge, StatusBadge } from '../components/Badges'
import { ErrorNote } from '../components/Panel'
import { useApi } from '../hooks/useApi'
import type { IncidentStream } from '../hooks/useEventStream'
import { formatDateTime, humanize } from '../lib/format'

const STATUSES: readonly IncidentStatus[] = [
  'detected',
  'investigating',
  'diagnosed',
  'planned',
  'awaiting_approval',
  'remediating',
  'verifying',
  'resolved',
  'failed',
]

const TYPES: readonly IncidentType[] = [
  'unhealthy_application',
  'traffic_spike',
  'high_cpu',
  'memory_pressure',
  'high_error_rate',
]

const CONTROL =
  'rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-200 transition hover:border-slate-500 focus:outline-none focus:ring-1 focus:ring-sky-500'

export function LiveListPage({ stream }: { stream: IncidentStream }) {
  const [status, setStatus] = useState<IncidentStatus | ''>('')
  const [type, setType] = useState<IncidentType | ''>('')

  const { data, error, loading, reload } = useApi(
    () => listIncidents({ status: status || undefined, type: type || undefined }),
    [status, type, stream.lastEvent, stream.reconnectEpoch],
  )

  const incidents = data ?? []
  const hasFilters = status !== '' || type !== ''

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-100">Live incidents</h1>
          <p className="text-sm text-slate-500">
            {incidents.length === 0 ? 'No incidents' : `${incidents.length} incident${incidents.length === 1 ? '' : 's'}`}
            {' · newest first'}
            {loading && data !== null && <span className="ml-2 text-sky-400">updating…</span>}
          </p>
        </div>

        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-xs text-slate-500">
            Status
            <select
              className={CONTROL}
              value={status}
              onChange={(event) => setStatus(event.target.value as IncidentStatus | '')}
            >
              <option value="">Any</option>
              {STATUSES.map((value) => (
                <option key={value} value={value}>
                  {humanize(value)}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-xs text-slate-500">
            Type
            <select
              className={CONTROL}
              value={type}
              onChange={(event) => setType(event.target.value as IncidentType | '')}
            >
              <option value="">Any</option>
              {TYPES.map((value) => (
                <option key={value} value={value}>
                  {humanize(value)}
                </option>
              ))}
            </select>
          </label>

          {hasFilters && (
            <button
              type="button"
              className={CONTROL}
              onClick={() => {
                setStatus('')
                setType('')
              }}
            >
              Clear
            </button>
          )}

          <button type="button" className={CONTROL} onClick={reload} disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      {error && <ErrorNote status={error.status} message={error.message} />}

      {data === null && loading && <p className="text-sm text-slate-500">Loading incidents…</p>}

      {data !== null && incidents.length === 0 && !hasFilters && <DemoIncidentCta />}

      {data !== null && incidents.length === 0 && hasFilters && (
        <div className="rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-6 text-center">
          <p className="text-sm text-slate-300">No incidents match these filters.</p>
          <button
            type="button"
            className={`${CONTROL} mt-3`}
            onClick={() => {
              setStatus('')
              setType('')
            }}
          >
            Clear filters
          </button>
        </div>
      )}

      {incidents.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-slate-800">
          <table className="w-full border-collapse text-left text-sm">
            <thead className="bg-slate-900/80 text-xs tracking-wide text-slate-500 uppercase">
              <tr>
                <th className="px-3 py-2 font-medium">Incident</th>
                <th className="px-3 py-2 font-medium">Type</th>
                <th className="px-3 py-2 font-medium">Severity</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Detected</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {incidents.map((incident) => (
                <tr key={incident.incident_id} className="bg-slate-950/40 hover:bg-slate-900/60">
                  <td className="px-3 py-2">
                    <Link
                      to={`/incidents/${encodeURIComponent(incident.incident_id)}`}
                      className="font-mono text-sky-400 hover:text-sky-300 hover:underline"
                    >
                      {incident.incident_id}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-slate-300">{humanize(incident.type)}</td>
                  <td className="px-3 py-2">
                    <SeverityBadge severity={incident.severity} />
                  </td>
                  <td className="px-3 py-2">
                    <StatusBadge status={incident.status} />
                  </td>
                  <td className="px-3 py-2 text-slate-400" title={incident.detected_at}>
                    {formatDateTime(incident.detected_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/**
 * The empty state. It must never be a blank screen, so it always offers the way
 * in — and in this slice the control is an explicit placeholder: the chaos fault
 * injection that actually creates the incident arrives with the console.
 */
function DemoIncidentCta() {
  return (
    <div className="rounded-lg border border-dashed border-slate-700 bg-slate-900/40 px-5 py-8 text-center">
      <h2 className="text-base font-semibold text-slate-100">No incidents yet</h2>
      <p className="mx-auto mt-1 max-w-xl text-sm text-slate-400">
        The dashboard is live and watching. A detected fault becomes an incident, and the incident
        then runs the whole lifecycle: investigate, diagnose, plan, wait for your approval,
        remediate, verify, and close.
      </p>
      <button
        type="button"
        disabled
        title="Placeholder — the chaos fault injection that creates the incident arrives with the console slice"
        className="mt-4 cursor-not-allowed rounded-md border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-400"
      >
        Generate demo incident
      </button>
      <p className="mx-auto mt-3 max-w-xl text-xs text-slate-500">
        Placeholder — this slice shows the call to action only. It does not post an incident; the
        next slice wires it to the simulated app&rsquo;s chaos trigger.
      </p>
    </div>
  )
}
