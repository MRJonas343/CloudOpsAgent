/**
 * The badges a status, severity, risk, and outcome share so one value reads the
 * same everywhere. Tailwind only sees literal class names, so the tone lookup
 * lives in `lib/format`.
 */

import type { ReactNode } from 'react'

import type {
  IncidentSeverity,
  IncidentStatus,
  RemediationOutcome,
  RunOutcome,
} from '../api/types'
import {
  type BadgeTone,
  humanize,
  outcomeTone,
  remediationTone,
  riskLabel,
  riskTone,
  severityTone,
  statusTone,
  toneClass,
} from '../lib/format'

interface BadgeProps {
  children: ReactNode
  tone?: BadgeTone
  title?: string
}

export function Badge({ children, tone = 'slate', title }: BadgeProps) {
  return (
    <span
      title={title}
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium tracking-wide uppercase ${toneClass(tone)}`}
    >
      {children}
    </span>
  )
}

export function StatusBadge({ status }: { status: IncidentStatus }) {
  return <Badge tone={statusTone(status)}>{humanize(status)}</Badge>
}

export function SeverityBadge({ severity }: { severity: IncidentSeverity }) {
  return <Badge tone={severityTone(severity)}>{severity}</Badge>
}

export function RiskBadge({ level }: { level: number }) {
  return (
    <Badge tone={riskTone(level)} title={`Risk level ${level}`}>
      {`Risk ${level} · ${riskLabel(level)}`}
    </Badge>
  )
}

export function OutcomeBadge({ outcome }: { outcome: RunOutcome }) {
  return <Badge tone={outcomeTone(outcome)}>{humanize(outcome)}</Badge>
}

export function RemediationBadge({ outcome }: { outcome: RemediationOutcome }) {
  return <Badge tone={remediationTone(outcome)}>{humanize(outcome)}</Badge>
}
