/**
 * Wire types for the agent and app read APIs.
 *
 * These mirror the pydantic models one-for-one (`cloudops_agent.models`,
 * `cloudops_agent.models.run`, `cloudops_app.models`). They are deliberately
 * hand-written rather than generated: the payloads are small, stable, and the
 * dashboard is read-only, so a generator would be more machinery than contract.
 */

export type IncidentType =
  | 'unhealthy_application'
  | 'traffic_spike'
  | 'high_cpu'
  | 'memory_pressure'
  | 'high_error_rate'

export type IncidentSeverity = 'low' | 'medium' | 'high' | 'critical'

export type IncidentStatus =
  | 'detected'
  | 'investigating'
  | 'diagnosed'
  | 'planned'
  | 'awaiting_approval'
  | 'remediating'
  | 'verifying'
  | 'resolved'
  | 'failed'

export type RunOutcome =
  | 'resolved'
  | 'verification_failed'
  | 'rejected'
  | 'timed_out'
  | 'error'
  | 'interrupted_restart'

export type RemediationOutcome = 'succeeded' | 'failed' | 'skipped'

export interface Observation {
  source: string
  summary: string
  metric: string
  value: number | null
  threshold: number | null
  observed_at: string
}

export interface Incident {
  incident_id: string
  service: string
  type: IncidentType
  severity: IncidentSeverity
  status: IncidentStatus
  detected_at: string
  observations: Observation[]
  source: string
  correlation_id: string
}

export interface TimelineEvent {
  phase: string
  status: IncidentStatus
  at: string
}

export interface Hypothesis {
  description: string
  confidence: number
  evidence: string[]
  created_at: string
}

export interface RemediationPlan {
  action: string
  description: string
  risk_level: number
  approval_required: boolean
  scope: string
  parameters: Record<string, unknown>
  rollback: string | null
  verification_criteria: string[]
  created_at: string
}

export interface ApprovalDecision {
  approved: boolean
  approver: string | null
  reason: string | null
  decided_at: string | null
  expires_at: string | null
}

export interface ApprovalRequest {
  incident_id: string
  action: string
  risk_level: number
  parameters: Record<string, unknown>
  requested_at: string
  deadline: string | null
  remaining_seconds: number | null
}

export interface RemediationResult {
  action: string
  outcome: RemediationOutcome
  executed_at: string
  output: string | null
  error: string | null
  verified: boolean | null
}

export interface VerificationResult {
  verified: boolean
  metrics_ok: boolean
  health_ok: boolean
  logs_ok: boolean
  summary: string
  checked_at: string
}

export interface RunRecord {
  incident_id: string
  status: IncidentStatus
  phase: string
  outcome: RunOutcome | null
  timeline: TimelineEvent[]
  observations: Observation[]
  hypotheses: Hypothesis[]
  diagnosis: string | null
  plan: RemediationPlan | null
  approval: ApprovalDecision | null
  approval_request: ApprovalRequest | null
  execution_result: RemediationResult | null
  verification: VerificationResult | null
  summary: string | null
  attempts: number
  approval_deadline: string | null
  started_at: string
  updated_at: string
  completed_at: string | null
}

/** The live countdown for a paused run; only present while a decision is pending. */
export interface ApprovalView {
  deadline: string
  remaining_seconds: number
}

/** `GET /incidents/{id}/report`: the full case file, partial while a run is in flight. */
export interface IncidentReport {
  incident: Incident | null
  run: RunRecord | null
  approval: ApprovalView | null
}

/** One SSE frame from `GET /events`. */
export interface IncidentEvent {
  incident_id: string
  type: IncidentType
  severity: IncidentSeverity
  status: IncidentStatus
  phase: string
  ts: string
  remaining_seconds: number | null
}

export interface DecisionBody {
  approver: string
  reason?: string
}

/** `GET /health` on the simulated app; `status` is `unhealthy` on a 503. */
export interface AppHealth {
  status: string
  service: string
}

/** `GET /metrics` on the simulated app. */
export interface AppMetrics {
  service: string
  status: string
  cpu_percent: number
  memory_percent: number
  request_count: number
  error_count: number
  error_rate: number
  latency_ms_p95: number
  requests_per_second: number
  replicas: number
}

/** The two faults the simulated app can inject (`cloudops_app.simulation.FaultMode`). */
export type FaultMode = 'traffic_spike' | 'unhealthy_application'

/**
 * `GET /simulate/status`, `POST /simulate/reset`, and `POST /simulate/{mode}`.
 *
 * `started_at` and `expires_at` are the app's `time.monotonic()` values, not
 * wall time, so they carry no clock meaning. The console renders
 * `remaining_seconds` and `duration_seconds` instead.
 */
export interface SimulationStatus {
  enabled: boolean
  mode: FaultMode | null
  started_at: number | null
  expires_at: number | null
  remaining_seconds: number | null
  duration_seconds: number | null
}
