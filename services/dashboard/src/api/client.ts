/**
 * The dashboard's whole network surface: four reads, two decisions, and the one
 * event stream URL. Every path is same-origin (`/api/agent`, `/api/app`), so
 * nginx owns the routing and no service needs CORS (ADR-006).
 */

import type {
  AppHealth,
  AppMetrics,
  DecisionBody,
  FaultMode,
  Incident,
  IncidentReport,
  IncidentStatus,
  IncidentType,
  RunRecord,
  SimulationStatus,
} from './types'

export const AGENT_BASE = '/api/agent'
export const APP_BASE = '/api/app'

/** The single `EventSource` target; the agent names its frames `incident`. */
export const EVENTS_URL = `${AGENT_BASE}/events`

export const EVENT_NAME = 'incident'

/** An HTTP failure carrying the status the UI needs to react to (e.g. 404, 409). */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export interface IncidentFilters {
  status?: IncidentStatus
  type?: IncidentType
}

async function readDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
  } catch {
    // A non-JSON body (a proxy error page, say) has nothing worth surfacing.
  }
  return `${response.status} ${response.statusText}`
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response))
  }
  return (await response.json()) as T
}

/** `GET /incidents?status=&type=` — newest-first, optionally filtered. */
export function listIncidents(filters: IncidentFilters = {}): Promise<Incident[]> {
  const query = new URLSearchParams()
  if (filters.status) query.set('status', filters.status)
  if (filters.type) query.set('type', filters.type)
  const queryString = query.toString()
  const suffix = queryString ? `?${queryString}` : ''
  return requestJson<Incident[]>(`${AGENT_BASE}/incidents${suffix}`)
}

/** `GET /incidents/{id}/report` — the case file, 404 only when both stores miss. */
export function getIncidentReport(incidentId: string): Promise<IncidentReport> {
  return requestJson<IncidentReport>(
    `${AGENT_BASE}/incidents/${encodeURIComponent(incidentId)}/report`,
  )
}

/** `POST /incidents/{id}/approve|reject` with the operator's decision. */
export function decideIncident(
  incidentId: string,
  decision: 'approve' | 'reject',
  body: DecisionBody,
): Promise<RunRecord> {
  return requestJson<RunRecord>(
    `${AGENT_BASE}/incidents/${encodeURIComponent(incidentId)}/${decision}`,
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    },
  )
}

/**
 * `GET /health` on the simulated app.
 *
 * A 503 is a *reading*, not a failure: the app answers 503 with a valid body to
 * report itself unhealthy, which is exactly the state the console must display.
 */
export async function getAppHealth(): Promise<AppHealth> {
  const response = await fetch(`${APP_BASE}/health`)
  if (!response.ok && response.status !== 503) {
    throw new ApiError(response.status, await readDetail(response))
  }
  return (await response.json()) as AppHealth
}

/** `GET /metrics` on the simulated app. */
export function getAppMetrics(): Promise<AppMetrics> {
  return requestJson<AppMetrics>(`${APP_BASE}/metrics`)
}

/** `GET /simulate/status` — the active fault; `403` when simulation is disabled. */
export function getSimulationStatus(): Promise<SimulationStatus> {
  return requestJson<SimulationStatus>(`${APP_BASE}/simulate/status`)
}

/** `POST /simulate/reset` — clear the active fault; `403` when disabled. */
export function resetSimulation(): Promise<SimulationStatus> {
  return requestJson<SimulationStatus>(`${APP_BASE}/simulate/reset`, { method: 'POST' })
}

/**
 * `POST /simulate/{mode}` — inject a *real* fault into the simulated app.
 *
 * This is the console's only way to make an incident happen: there is no
 * `POST /incidents` call anywhere in the dashboard, so whatever the live list
 * shows was found and reported by the Monitor, not posted by the UI. A refused
 * injection surfaces as an `ApiError` (`403` disabled, `404` unknown mode).
 */
export function injectFault(mode: FaultMode, durationSeconds?: number): Promise<SimulationStatus> {
  const init: RequestInit = { method: 'POST' }
  // The route takes an optional body; sending `content-type: application/json`
  // with an empty body would make the app fail to parse it, so the header only
  // appears when there is something to parse.
  if (durationSeconds !== undefined) {
    init.headers = { 'content-type': 'application/json' }
    init.body = JSON.stringify({ duration_seconds: durationSeconds })
  }
  return requestJson<SimulationStatus>(`${APP_BASE}/simulate/${mode}`, init)
}
