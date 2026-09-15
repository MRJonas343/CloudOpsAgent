/**
 * A numbered case-file section. The `step` is what makes the reading order —
 * timeline, evidence, hypotheses, diagnosis, plan, approval, execution,
 * verification, post-mortem — visible at a glance rather than implied.
 */

import type { ReactNode } from 'react'

interface PanelProps {
  step?: number
  title: string
  hint?: ReactNode
  children: ReactNode
}

export function Panel({ step, title, hint, children }: PanelProps) {
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900/50">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-slate-800 px-4 py-2.5">
        {step !== undefined && (
          <span className="font-mono text-xs text-slate-500">{String(step).padStart(2, '0')}</span>
        )}
        <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
        {hint && <span className="text-xs text-slate-500">{hint}</span>}
      </header>
      <div className="px-4 py-3.5 text-sm text-slate-300">{children}</div>
    </section>
  )
}

/** The one-line fallback for a section that a partial (in-flight) run has not reached. */
export function NotYet({ children }: { children: ReactNode }) {
  return <p className="text-sm text-slate-500 italic">{children}</p>
}

/**
 * A read that failed. The status is shown when there is one, because `404` on a
 * case file and a transport failure mean different things to the operator.
 */
export function ErrorNote({ status, message }: { status: number | null; message: string }) {
  return (
    <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3.5 py-2.5 text-sm text-rose-200">
      <span className="font-semibold">
        {status === null ? 'Could not reach the API' : `Request failed (${status})`}
      </span>
      {' — '}
      {message}
    </div>
  )
}
