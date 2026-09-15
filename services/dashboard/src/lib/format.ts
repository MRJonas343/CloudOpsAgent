/**
 * Presentation helpers: enum labels, timestamps, numbers, and the class maps the
 * badges share. Kept in one module so a status reads the same colour everywhere.
 */

import type {
  IncidentSeverity,
  IncidentStatus,
  RemediationOutcome,
  RunOutcome,
} from '../api/types'

/** `awaiting_approval` -> `Awaiting approval`; `analyze_incident` -> `Analyze incident`. */
export function humanize(value: string | null | undefined): string {
  if (!value) return '—'
  const words = value.replace(/_/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** Short local time, used inside timelines where the date is already established. */
export function formatTime(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/** Local date and time; the ISO value stays available via the caller's `title`. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

/** `28` -> `0:28`, for the approval countdown. */
export function formatCountdown(seconds: number): string {
  const clamped = Math.max(0, Math.floor(seconds))
  const minutes = Math.floor(clamped / 60)
  const remainder = clamped % 60
  return `${minutes}:${remainder.toString().padStart(2, '0')}`
}

export function formatNumber(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return '—'
  return value.toFixed(digits)
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

/** A metric observation reads `12.4 / 20` when it has a threshold, `12.4` otherwise. */
export function formatObservation(value: number | null, threshold: number | null): string | null {
  if (value === null) return null
  if (threshold === null) return formatNumber(value, 2)
  return `${formatNumber(value, 2)} / ${formatNumber(threshold, 2)}`
}

export type BadgeTone = 'sky' | 'indigo' | 'violet' | 'amber' | 'cyan' | 'teal' | 'emerald' | 'rose' | 'slate'

/** Literal class strings only: Tailwind scans source text, not computed names. */
const TONES: Record<BadgeTone, string> = {
  sky: 'border-sky-500/40 bg-sky-500/10 text-sky-300',
  indigo: 'border-indigo-500/40 bg-indigo-500/10 text-indigo-300',
  violet: 'border-violet-500/40 bg-violet-500/10 text-violet-300',
  amber: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
  cyan: 'border-cyan-500/40 bg-cyan-500/10 text-cyan-300',
  teal: 'border-teal-500/40 bg-teal-500/10 text-teal-300',
  emerald: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
  rose: 'border-rose-500/40 bg-rose-500/10 text-rose-300',
  slate: 'border-slate-600/50 bg-slate-600/10 text-slate-300',
}

export function toneClass(tone: BadgeTone): string {
  return TONES[tone]
}

const STATUS_TONES: Record<IncidentStatus, BadgeTone> = {
  detected: 'sky',
  investigating: 'indigo',
  diagnosed: 'violet',
  planned: 'violet',
  awaiting_approval: 'amber',
  remediating: 'cyan',
  verifying: 'teal',
  resolved: 'emerald',
  failed: 'rose',
}

export function statusTone(status: IncidentStatus): BadgeTone {
  return STATUS_TONES[status]
}

const SEVERITY_TONES: Record<IncidentSeverity, BadgeTone> = {
  low: 'slate',
  medium: 'amber',
  high: 'rose',
  critical: 'rose',
}

export function severityTone(severity: IncidentSeverity): BadgeTone {
  return SEVERITY_TONES[severity]
}

/** Risk 0-3 per ADR-004. */
const RISK_LABELS = ['Read-only', 'Safe remediation', 'Infrastructure change', 'Destructive']

export function riskLabel(level: number): string {
  return RISK_LABELS[level] ?? `Risk ${level}`
}

export function riskTone(level: number): BadgeTone {
  if (level >= 3) return 'rose'
  if (level === 2) return 'amber'
  if (level === 1) return 'sky'
  return 'slate'
}

const OUTCOME_TONES: Record<RunOutcome, BadgeTone> = {
  resolved: 'emerald',
  verification_failed: 'rose',
  rejected: 'rose',
  timed_out: 'amber',
  error: 'rose',
  interrupted_restart: 'amber',
}

export function outcomeTone(outcome: RunOutcome): BadgeTone {
  return OUTCOME_TONES[outcome]
}

const REMEDIATION_TONES: Record<RemediationOutcome, BadgeTone> = {
  succeeded: 'emerald',
  failed: 'rose',
  skipped: 'slate',
}

export function remediationTone(outcome: RemediationOutcome): BadgeTone {
  return REMEDIATION_TONES[outcome]
}

/** Short clock time for a unix-seconds value (the app's simulation timestamps). */
export function formatEpochSeconds(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return new Date(value * 1000).toLocaleTimeString()
}
