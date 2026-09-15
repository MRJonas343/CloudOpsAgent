/**
 * The in-app notification stack. Announcements are polite (`aria-live`), so a
 * screen reader hears them without being interrupted mid-thought, and each toast
 * can be dismissed early.
 */

import { statusTone, toneClass } from '../lib/format'
import type { Toast } from '../hooks/useToasts'

interface ToastStackProps {
  toasts: Toast[]
  onDismiss: (id: number) => void
}

export function ToastStack({ toasts, onDismiss }: ToastStackProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 top-3 z-50 flex flex-col items-center gap-2 px-3 sm:inset-x-auto sm:right-4 sm:items-end"
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-lg border px-3.5 py-2.5 shadow-lg backdrop-blur ${toneClass(statusTone(toast.status))}`}
        >
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold">{toast.title}</p>
            <p className="mt-0.5 text-xs text-slate-400">{toast.detail}</p>
          </div>
          <button
            type="button"
            onClick={() => onDismiss(toast.id)}
            aria-label={`Dismiss notification for ${toast.incidentId}`}
            className="rounded px-1 text-slate-400 transition hover:text-slate-100"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  )
}
