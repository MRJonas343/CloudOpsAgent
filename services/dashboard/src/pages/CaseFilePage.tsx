/**
 * `/incidents/:id` — the case file.
 *
 * One read of `GET /incidents/{id}/report`, refreshed on every frame that
 * belongs to this incident and on every stream reconnect. The sections are
 * rendered in the order the run produces them — timeline, evidence, hypotheses,
 * diagnosis, plan, approval, execution, verification, post-mortem — so the page
 * reads as the story of the incident rather than as a bag of fields.
 *
 * A run in flight returns a partial report, so every section has an honest
 * "not reached yet" state instead of disappearing.
 */

import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { decideIncident, getIncidentReport } from '../api/client'
import type {
  ApprovalDecision,
  IncidentReport,
  Observation,
  RemediationPlan,
  RunRecord,
} from '../api/types'
import {
  Badge,
  OutcomeBadge,
  RemediationBadge,
  RiskBadge,
  SeverityBadge,
  StatusBadge,
} from '../components/Badges'
import { ErrorNote, NotYet, Panel } from '../components/Panel'
import { Field, Prose } from '../components/Prose'
import { useApi } from '../hooks/useApi'
import { useCountdown } from '../hooks/useCountdown'
import type { IncidentStream } from '../hooks/useEventStream'
import {
  formatCountdown,
  formatDateTime,
  formatObservation,
  formatPercent,
  formatTime,
  humanize,
} from '../lib/format'

export function CaseFilePage({ stream }: { stream: IncidentStream }) {
  const { id = '' } = useParams<{ id: string }>()

  // Every frame is delivered, including the `resolved` the runner publishes a
  // second time when it finalises the record; the key changes per frame so the
  // second one refreshes the case file and picks up the outcome and completion
  // time. Frames for other incidents leave the key alone.
  const frame = stream.lastEvent
  const frameKey = frame && frame.incident_id === id ? `${frame.status}:${frame.ts}` : ''

  const { data: report, error, loading, reload } = useApi(
    () => getIncidentReport(id),
    [id, frameKey, stream.reconnectEpoch],
  )

  if (error?.status === 404) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/50 px-5 py-8 text-center">
        <h1 className="text-base font-semibold text-slate-100">Incident {id} was not found</h1>
        <p className="mt-1 text-sm text-slate-400">
          Neither the incident store nor the run store knows this id.
        </p>
        <Link to="/" className="mt-4 inline-block text-sm text-sky-400 hover:text-sky-300 hover:underline">
          ← Back to live incidents
        </Link>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-3">
        <ErrorNote status={error.status} message={error.message} />
        <button
          type="button"
          className="rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-200 hover:border-slate-500"
          onClick={reload}
        >
          Retry
        </button>
      </div>
    )
  }

  if (report === null) {
    return <p className="text-sm text-slate-500">{loading ? 'Loading case file…' : 'No data.'}</p>
  }

  const { incident, run } = report
  const evidence = selectEvidence(run, incident?.observations ?? [])

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Link to="/" className="text-xs text-slate-500 hover:text-slate-300">
            ← All incidents
          </Link>
          <h1 className="mt-1 flex flex-wrap items-center gap-2">
            <span className="font-mono text-xl text-slate-100">{id}</span>
            {incident && <StatusBadge status={incident.status} />}
            {incident && <SeverityBadge severity={incident.severity} />}
            {run?.outcome && <OutcomeBadge outcome={run.outcome} />}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            {incident ? `${humanize(incident.type)} · ${incident.service}` : 'incident record unavailable'}
            {incident && ` · detected ${formatDateTime(incident.detected_at)}`}
          </p>
        </div>

        <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-slate-500 sm:grid-cols-3">
          <Meta label="Current phase" value={humanize(run?.phase)} />
          <Meta label="Attempts" value={run ? String(run.attempts) : '—'} />
          <Meta label="Started" value={formatDateTime(run?.started_at)} />
          <Meta label="Last update" value={formatDateTime(run?.updated_at)} />
          <Meta label="Completed" value={formatDateTime(run?.completed_at)} />
        </dl>
      </header>

      {run === null && (
        <p className="rounded-lg border border-slate-800 bg-slate-900/40 px-3.5 py-2.5 text-sm text-slate-400">
          No run has been recorded for this incident yet.
        </p>
      )}

      <Panel step={1} title="Timeline" hint="how the run actually moved">
        <TimelineSection run={run} />
      </Panel>

      <Panel step={2} title="Evidence" hint={`${evidence.length} observation${evidence.length === 1 ? '' : 's'}`}>
        <EvidenceSection observations={evidence} />
      </Panel>

      <Panel step={3} title="Hypotheses" hint="what the evidence could mean">
        <HypothesesSection run={run} />
      </Panel>

      <Panel step={4} title="Diagnosis" hint="the best-supported cause">
        <DiagnosisSection run={run} />
      </Panel>

      <Panel step={5} title="Plan" hint="the proposed remediation">
        <PlanSection plan={run?.plan ?? null} />
      </Panel>

      <Panel step={6} title="Approval" hint="the operator's decision">
        <ApprovalSection incidentId={id} report={report} onSettled={reload} />
      </Panel>

      <Panel step={7} title="Execution" hint="what was actually run">
        <ExecutionSection run={run} />
      </Panel>

      <Panel step={8} title="Verification" hint="evidence the fix worked">
        <VerificationSection run={run} />
      </Panel>

      <Panel step={9} title="Post-mortem" hint="the closing summary">
        {run?.summary ? (
          <Prose text={run.summary} />
        ) : (
          <NotYet>The post-mortem is written when the run closes.</NotYet>
        )}
      </Panel>
    </div>
  )
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="tracking-wide uppercase">{label}</dt>
      <dd className="text-slate-300">{value}</dd>
    </div>
  )
}

/**
 * The run's own accumulated evidence is the fuller list; the incident's
 * monitor-captured observations are the fallback for a run that never started.
 */
function selectEvidence(run: RunRecord | null, incidentObservations: Observation[]): Observation[] {
  if (run && run.observations.length > 0) return run.observations
  return incidentObservations
}

function TimelineSection({ run }: { run: RunRecord | null }) {
  const timeline = run?.timeline ?? []
  if (timeline.length === 0) {
    return <NotYet>The run has not stepped through a phase yet.</NotYet>
  }

  return (
    <ol>
      {timeline.map((event, index) => {
        const isLast = index === timeline.length - 1
        return (
          <li key={`${index}-${event.phase}-${event.at}`} className="flex gap-3">
            <span className="flex flex-col items-center pt-1.5">
              <span
                className={`h-2.5 w-2.5 shrink-0 rounded-full ${
                  isLast ? 'bg-sky-400 ring-2 ring-sky-400/30' : 'bg-slate-600'
                }`}
              />
              {!isLast && <span className="w-px flex-1 bg-slate-800" />}
            </span>
            <div className={`flex flex-1 flex-wrap items-center gap-x-3 gap-y-1 ${isLast ? 'pb-0' : 'pb-3'}`}>
              <span className="text-sm text-slate-200">{humanize(event.phase)}</span>
              <StatusBadge status={event.status} />
              <span className="font-mono text-xs text-slate-500" title={event.at}>
                {formatTime(event.at)}
              </span>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

function EvidenceSection({ observations }: { observations: Observation[] }) {
  if (observations.length === 0) {
    return <NotYet>No observations were collected.</NotYet>
  }

  return (
    <ul className="space-y-2">
      {observations.map((observation, index) => {
        const measured = formatObservation(observation.value, observation.threshold)
        return (
          <li
            key={`${index}-${observation.metric}-${observation.observed_at}`}
            className="rounded-md border border-slate-800 bg-slate-950/40 px-3 py-2"
          >
            <div className="flex items-baseline justify-between gap-3">
              <p className="text-slate-200">{observation.summary}</p>
              <span className="shrink-0 font-mono text-xs text-slate-500" title={observation.observed_at}>
                {formatTime(observation.observed_at)}
              </span>
            </div>
            <p className="mt-0.5 text-xs text-slate-500">
              <span className="font-mono">{observation.source}</span> · {observation.metric}
              {measured && (
                <>
                  {' = '}
                  <span className="font-mono text-slate-300">{measured}</span>
                  {observation.threshold !== null && <span className="ml-1">(value / threshold)</span>}
                </>
              )}
            </p>
          </li>
        )
      })}
    </ul>
  )
}

function HypothesesSection({ run }: { run: RunRecord | null }) {
  const hypotheses = run?.hypotheses ?? []
  if (hypotheses.length === 0) {
    return <NotYet>No hypotheses were recorded.</NotYet>
  }

  return (
    <ul className="space-y-3">
      {hypotheses.map((hypothesis, index) => (
        <li key={`${index}-${hypothesis.created_at}`} className="rounded-md border border-slate-800 bg-slate-950/40 px-3 py-2">
          <p className="text-slate-200">{hypothesis.description}</p>
          <div className="mt-1.5 flex items-center gap-2">
            <span className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-800">
              <span
                className="block h-full rounded-full bg-violet-400"
                style={{ width: `${Math.round(hypothesis.confidence * 100)}%` }}
              />
            </span>
            <span className="text-xs text-slate-500">
              confidence {formatPercent(hypothesis.confidence, 0)}
            </span>
          </div>
          {hypothesis.evidence.length > 0 && (
            <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-xs text-slate-400">
              {hypothesis.evidence.map((item, evidenceIndex) => (
                <li key={evidenceIndex}>{item}</li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ul>
  )
}

function DiagnosisSection({ run }: { run: RunRecord | null }) {
  if (!run?.diagnosis) return <NotYet>The run has not reached a diagnosis yet.</NotYet>
  return <Prose text={run.diagnosis} />
}

function PlanSection({ plan }: { plan: RemediationPlan | null }) {
  if (!plan) return <NotYet>The run has not produced a remediation plan yet.</NotYet>

  const parameters = Object.entries(plan.parameters)

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-slate-100">{plan.action}</span>
        <RiskBadge level={plan.risk_level} />
        <Badge tone={plan.approval_required ? 'amber' : 'slate'}>
          {plan.approval_required ? 'Approval required' : 'No approval required'}
        </Badge>
      </div>

      <Prose text={plan.description} />

      <dl className="divide-y divide-slate-800/70">
        <Field label="Scope">{plan.scope}</Field>
        <Field label="Rollback">{plan.rollback ?? 'Not stated'}</Field>
        <Field label="Created">{formatDateTime(plan.created_at)}</Field>
      </dl>

      {parameters.length > 0 && (
        <div>
          <p className="mb-1 text-xs tracking-wide text-slate-500 uppercase">Parameters</p>
          <dl className="divide-y divide-slate-800/70">
            {parameters.map(([key, value]) => (
              <Field key={key} label={key}>
                <span className="font-mono text-xs">{renderParameter(value)}</span>
              </Field>
            ))}
          </dl>
        </div>
      )}

      {plan.verification_criteria.length > 0 && (
        <div>
          <p className="mb-1 text-xs tracking-wide text-slate-500 uppercase">
            Verification criteria
          </p>
          <ul className="list-disc space-y-0.5 pl-5">
            {plan.verification_criteria.map((criterion, index) => (
              <li key={index}>{criterion}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function renderParameter(value: unknown): string {
  if (typeof value === 'string') return value
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value)
}

function ApprovalSection({
  incidentId,
  report,
  onSettled,
}: {
  incidentId: string
  report: IncidentReport
  onSettled: () => void
}) {
  const [approver, setApprover] = useState('operator')
  const [reason, setReason] = useState('')
  const [pending, setPending] = useState<'approve' | 'reject' | null>(null)
  const [failure, setFailure] = useState<string | null>(null)

  const remaining = useCountdown(report.approval?.remaining_seconds ?? null)
  const request = report.run?.approval_request ?? null
  const plan = report.run?.plan ?? null
  const decision = report.run?.approval ?? null

  async function submit(kind: 'approve' | 'reject') {
    const name = approver.trim()
    if (name === '') {
      setFailure('An approver name is required.')
      return
    }
    setPending(kind)
    setFailure(null)
    try {
      await decideIncident(incidentId, kind, {
        approver: name,
        ...(reason.trim() === '' ? {} : { reason: reason.trim() }),
      })
    } catch (error) {
      // A 409 means the pause was already resolved (most often by the timeout
      // sweeper); either way the page reloads below and shows the truth.
      setFailure(error instanceof Error ? error.message : 'The decision could not be sent.')
    } finally {
      setPending(null)
      onSettled()
    }
  }

  if (!report.approval) {
    if (decision) return <RecordedDecision decision={decision} />
    return (
      <NotYet>
        {plan?.approval_required
          ? 'The approval gate has been passed.'
          : 'No approval was required for this run.'}
      </NotYet>
    )
  }

  const action = request?.action ?? plan?.action ?? 'the proposed action'
  const risk = request?.risk_level ?? plan?.risk_level ?? 0
  const parameters = Object.entries(request?.parameters ?? plan?.parameters ?? {})
  const expired = remaining !== null && remaining <= 0

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-3.5 py-3">
        <div>
          <p className="text-xs tracking-wide text-amber-300 uppercase">Decision pending</p>
          <p className="mt-0.5 text-slate-100">
            Approve or reject <span className="font-mono">{action}</span>
          </p>
        </div>
        <div className="text-right">
          <p
            className="font-mono text-2xl text-amber-200"
            title={report.approval ? `Deadline ${report.approval.deadline}` : undefined}
          >
            {formatCountdown(remaining ?? 0)}
          </p>
          <p className="text-xs text-amber-300/80">
            {expired ? 'deadline passed' : 'time left to decide'}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <RiskBadge level={risk} />
        {plan?.scope && <span className="text-slate-400">Scope: {plan.scope}</span>}
      </div>

      {parameters.length > 0 && (
        <dl className="divide-y divide-slate-800/70">
          {parameters.map(([key, value]) => (
            <Field key={key} label={key}>
              <span className="font-mono text-xs">{renderParameter(value)}</span>
            </Field>
          ))}
        </dl>
      )}

      <div className="grid gap-2 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs text-slate-500">
          Approver
          <input
            className="rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
            value={approver}
            onChange={(event) => setApprover(event.target.value)}
            placeholder="your name"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-500">
          Reason (optional)
          <input
            className="rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="why you are deciding this way"
          />
        </label>
      </div>

      {failure && (
        <p className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
          {failure}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={pending !== null}
          onClick={() => void submit('approve')}
          className="rounded-md border border-emerald-500/50 bg-emerald-500/15 px-4 py-1.5 text-sm font-medium text-emerald-200 transition hover:bg-emerald-500/25 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pending === 'approve' ? 'Approving…' : 'Approve and execute'}
        </button>
        <button
          type="button"
          disabled={pending !== null}
          onClick={() => void submit('reject')}
          className="rounded-md border border-rose-500/50 bg-rose-500/15 px-4 py-1.5 text-sm font-medium text-rose-200 transition hover:bg-rose-500/25 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pending === 'reject' ? 'Rejecting…' : 'Reject'}
        </button>
      </div>

      <p className="text-xs text-slate-500">
        Rejecting ends the run without executing anything. If the countdown runs out the run is
        also ended, through the same rejection path.
      </p>
    </div>
  )
}

function RecordedDecision({ decision }: { decision: ApprovalDecision }) {
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={decision.approved ? 'emerald' : 'rose'}>
          {decision.approved ? 'Approved' : 'Rejected'}
        </Badge>
        <span className="text-xs text-slate-500">
          {decision.approver ? `by ${decision.approver}` : 'no operator decision'}
          {decision.decided_at ? ` · ${formatDateTime(decision.decided_at)}` : ''}
        </span>
      </div>
      {decision.reason && <p className="text-slate-300">Reason: {decision.reason}</p>}
    </div>
  )
}

function ExecutionSection({ run }: { run: RunRecord | null }) {
  const result = run?.execution_result
  if (!result) {
    if (run?.approval && !run.approval.approved) {
      return <NotYet>No action was executed: the plan was not approved.</NotYet>
    }
    if (run?.plan) return <NotYet>Nothing has been executed yet.</NotYet>
    return <NotYet>The run has not produced a remediation plan yet.</NotYet>
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-slate-100">{result.action}</span>
        <RemediationBadge outcome={result.outcome} />
        {result.verified === true && <Badge tone="emerald">verified</Badge>}
        {result.verified === false && <Badge tone="rose">not verified</Badge>}
      </div>

      <dl className="divide-y divide-slate-800/70">
        <Field label="Executed">{formatDateTime(result.executed_at)}</Field>
      </dl>

      {result.output && (
        <div>
          <p className="mb-1 text-xs tracking-wide text-slate-500 uppercase">Output</p>
          <pre className="overflow-x-auto rounded-md border border-slate-800 bg-slate-950/60 p-3 font-mono text-xs whitespace-pre-wrap text-slate-300">
            {result.output}
          </pre>
        </div>
      )}

      {result.error && (
        <div>
          <p className="mb-1 text-xs tracking-wide text-slate-500 uppercase">Error</p>
          <p className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
            {result.error}
          </p>
        </div>
      )}
    </div>
  )
}

function VerificationSection({ run }: { run: RunRecord | null }) {
  const verification = run?.verification
  if (!verification) return <NotYet>Verification has not run yet.</NotYet>

  const checks: Array<[string, boolean]> = [
    ['Metrics within thresholds', verification.metrics_ok],
    ['Health reporting ok', verification.health_ok],
    ['No error-level logs', verification.logs_ok],
  ]

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={verification.verified ? 'emerald' : 'rose'}>
          {verification.verified ? 'Verification passed' : 'Verification failed'}
        </Badge>
        <span className="text-xs text-slate-500">{formatDateTime(verification.checked_at)}</span>
      </div>

      <ul className="space-y-1">
        {checks.map(([label, ok]) => (
          <li key={label} className="flex items-center gap-2">
            <span className={ok ? 'text-emerald-400' : 'text-rose-400'} aria-hidden="true">
              {ok ? '✓' : '✗'}
            </span>
            <span className="text-slate-300">{label}</span>
            <span className="sr-only">{ok ? 'passed' : 'failed'}</span>
          </li>
        ))}
      </ul>

      <Prose text={verification.summary} />
    </div>
  )
}
