/**
 * The app shell: one `EventSource` for the whole surface, three routes, and the
 * notification stack.
 *
 * The stream is opened here and passed down, which is what keeps it to a single
 * connection: the live list, the open case file, the toasts, and the chaos
 * trigger all react to the same frames instead of each opening their own stream.
 * The chaos trigger lives here too, so an injection started from the empty-state
 * call to action is still pending when the operator opens `/console`.
 */

import { NavLink, Navigate, Route, Routes } from 'react-router-dom'

import { ToastStack } from './components/Toasts'
import { useChaos } from './hooks/useChaos'
import { useEventStream } from './hooks/useEventStream'
import { useToasts } from './hooks/useToasts'
import { CaseFilePage } from './pages/CaseFilePage'
import { ConsolePage } from './pages/ConsolePage'
import { LiveListPage } from './pages/LiveListPage'
import type { ConnectionState } from './hooks/useEventStream'

export default function App() {
  const { toasts, notify, dismiss } = useToasts()
  const stream = useEventStream(notify)
  // One chaos trigger for the whole surface: the empty-state call to action and
  // the console drive the same injection, and the pending state survives moving
  // between them.
  const chaos = useChaos(stream)

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200">
      <header className="border-b border-slate-800 bg-slate-950/90">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex flex-wrap items-center gap-5">
            <span className="text-sm font-semibold tracking-tight text-slate-100">
              CloudOpsAgent
              <span className="ml-2 font-normal text-slate-500">incident console</span>
            </span>
            <nav className="flex items-center gap-1">
              <NavItem to="/">Live incidents</NavItem>
              <NavItem to="/console">Application</NavItem>
            </nav>
          </div>
          <ConnectionBadge connection={stream.connection} />
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-5">
        <Routes>
          <Route path="/" element={<LiveListPage stream={stream} chaos={chaos} />} />
          <Route path="/incidents/:id" element={<CaseFilePage stream={stream} />} />
          <Route path="/console" element={<ConsolePage chaos={chaos} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </div>
  )
}

function NavItem({ to, children }: { to: string; children: string }) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      className={({ isActive }) =>
        `rounded-md px-2.5 py-1.5 text-sm transition ${
          isActive ? 'bg-slate-800 text-slate-100' : 'text-slate-400 hover:text-slate-200'
        }`
      }
    >
      {children}
    </NavLink>
  )
}

const CONNECTION: Record<ConnectionState, { label: string; dot: string }> = {
  connecting: { label: 'connecting', dot: 'bg-slate-500' },
  live: { label: 'live', dot: 'bg-emerald-400' },
  reconnecting: { label: 'reconnecting', dot: 'bg-amber-400' },
}

/**
 * The stream state is worth showing: a dashboard that has quietly lost its
 * connection looks identical to a quiet system, and those mean very different
 * things to an operator.
 */
function ConnectionBadge({ connection }: { connection: ConnectionState }) {
  const { label, dot } = CONNECTION[connection]
  const animated = connection !== 'live' ? 'animate-pulse' : ''
  return (
    <span className="flex items-center gap-2 rounded-full border border-slate-800 px-2.5 py-1 text-xs text-slate-400">
      <span className={`h-2 w-2 rounded-full ${dot} ${animated}`} />
      event stream: {label}
    </span>
  )
}
