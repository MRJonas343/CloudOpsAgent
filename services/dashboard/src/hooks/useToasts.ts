/**
 * The in-app notifications: exactly the four lifecycle moments worth
 * interrupting an operator for, and nothing else.
 *
 * The four are `detected`, `awaiting_approval`, `resolved`, and `failed`. Every
 * other status (`investigating` -> `diagnosed`, and so on) is silent, and the
 * per-incident memory of the last status is what makes a repeated frame — a
 * `resolved` published twice by the same run — raise only one toast.
 *
 * The last status is recorded even for the silent statuses, so a real second
 * pause later in a retried run (a different status in between) notifies again
 * rather than being swallowed by the dedupe.
 */

import { useCallback, useRef, useState } from 'react'

import type { IncidentEvent, IncidentStatus } from '../api/types'
import { humanize } from '../lib/format'

/** How long a toast stays before it dismisses itself. */
const TOAST_TTL_MS = 6000

/** Keep the stack short; older toasts fall off rather than cover the page. */
const MAX_TOASTS = 5

export type ToastableStatus = 'detected' | 'awaiting_approval' | 'resolved' | 'failed'

const TOASTABLE_STATUSES: readonly ToastableStatus[] = [
  'detected',
  'awaiting_approval',
  'resolved',
  'failed',
]

function isToastable(status: IncidentStatus): status is ToastableStatus {
  return (TOASTABLE_STATUSES as readonly IncidentStatus[]).includes(status)
}

export interface Toast {
  id: number
  status: ToastableStatus
  incidentId: string
  title: string
  detail: string
}

function buildToast(id: number, event: IncidentEvent, status: ToastableStatus): Toast {
  const base = { id, status, incidentId: event.incident_id }
  switch (status) {
    case 'detected':
      return {
        ...base,
        title: `Incident detected — ${event.incident_id}`,
        detail: `${humanize(event.type)} · ${event.severity} severity · under investigation`,
      }
    case 'awaiting_approval':
      return {
        ...base,
        title: `Approval required — ${event.incident_id}`,
        detail:
          event.remaining_seconds === null
            ? 'A remediation plan is waiting for your decision'
            : `A remediation plan is waiting — ${event.remaining_seconds}s left to decide`,
      }
    case 'resolved':
      return {
        ...base,
        title: `Incident resolved — ${event.incident_id}`,
        detail: 'Remediation verified and the incident closed',
      }
    case 'failed':
      return {
        ...base,
        title: `Incident failed — ${event.incident_id}`,
        detail: 'The run ended without a verified resolution',
      }
  }
}

export interface ToastController {
  toasts: Toast[]
  notify: (event: IncidentEvent) => void
  dismiss: (id: number) => void
}

export function useToasts(): ToastController {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(1)
  const lastStatusByIncident = useRef(new Map<string, IncidentStatus>())

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const notify = useCallback(
    (event: IncidentEvent) => {
      const previous = lastStatusByIncident.current.get(event.incident_id)
      lastStatusByIncident.current.set(event.incident_id, event.status)

      // The dedupe: a frame repeating the incident's current status is not a new
      // lifecycle moment, and only the four toastable ones are announced at all.
      if (previous === event.status || !isToastable(event.status)) return

      const id = nextId.current
      nextId.current += 1
      const toast = buildToast(id, event, event.status)
      setToasts((current) => [...current, toast].slice(-MAX_TOASTS))
      window.setTimeout(() => dismiss(id), TOAST_TTL_MS)
    },
    [dismiss],
  )

  return { toasts, notify, dismiss }
}
