/**
 * The chaos console's state machine: inject one real fault, then wait honestly
 * for the agent to find it.
 *
 * The console owns no incidents. It calls the simulated app's own `/simulate`
 * routes through the same origin and then reads the shared event stream, so the
 * only thing that can ever turn an injection into an incident is the Monitor
 * detecting the degraded app and reporting it. The phases say exactly where that
 * is:
 *
 * - `injecting` — the request is in flight.
 * - `pending`   — the app accepted the fault; the agent has not reported it yet
 *                 (detection is one poll interval away, ~10s by default).
 * - `reported`  — the agent published a `detected` frame for a *new* incident of
 *                 the injected type. This is the only path that names an incident.
 * - `undetected`— the fault lapsed before anything was reported, so the console
 *                 says so rather than inventing a result.
 *
 * A refused injection (`403` when the simulation is disabled, `404` for an
 * unknown mode) lands in `error` and changes nothing else: no phase advance, no
 * incident, no silent success.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { getSimulationStatus, injectFault, resetSimulation } from '../api/client'
import type { FaultMode, SimulationStatus } from '../api/types'
import { type ApiFailure, describeError } from './useApi'
import type { IncidentStream } from './useEventStream'

/** How often the active-fault read is refreshed while the dashboard is open. */
const STATUS_POLL_MS = 5000

export type ChaosPhase = 'idle' | 'injecting' | 'pending' | 'reported' | 'undetected'

export interface ChaosController {
  phase: ChaosPhase
  /** The fault being injected, held until the phase returns to `idle`. */
  mode: FaultMode | null
  /** When the app accepted the injection (client clock, for the elapsed readout). */
  injectedAt: number | null
  /** The incident the agent reported for this injection, once it has. */
  incidentId: string | null
  /** The last refused injection, if any; cleared on the next attempt. */
  error: ApiFailure | null
  simulation: SimulationStatus | null
  simulationError: ApiFailure | null
  simulationLoading: boolean
  inject: (mode: FaultMode, durationSeconds?: number) => Promise<void>
  reset: () => Promise<void>
}

export function useChaos(stream: IncidentStream): ChaosController {
  const [phase, setPhase] = useState<ChaosPhase>('idle')
  const [mode, setMode] = useState<FaultMode | null>(null)
  const [injectedAt, setInjectedAt] = useState<number | null>(null)
  const [incidentId, setIncidentId] = useState<string | null>(null)
  const [error, setError] = useState<ApiFailure | null>(null)

  const [simulation, setSimulation] = useState<SimulationStatus | null>(null)
  const [simulationError, setSimulationError] = useState<ApiFailure | null>(null)
  const [simulationLoading, setSimulationLoading] = useState(true)

  // Every incident id the stream has shown, and the set that was already known
  // when the current injection started. Resolving on "detected, right type, and
  // an id we had not seen" needs no clock agreement between browser and agent,
  // and cannot be triggered by a frame that was already on the wire.
  const knownIncidents = useRef(new Set<string>())
  const knownAtInjection = useRef(new Set<string>())

  // A status read that started before an injection must not land afterwards and
  // overwrite the injected state, so inject/reset bump the generation and any
  // in-flight read whose generation is stale is dropped.
  const generation = useRef(0)

  const refreshSimulation = useCallback(async () => {
    const request = ++generation.current
    try {
      const status = await getSimulationStatus()
      if (request !== generation.current) return
      setSimulation(status)
      setSimulationError(null)
    } catch (failure: unknown) {
      if (request !== generation.current) return
      setSimulationError(describeError(failure))
    } finally {
      if (request === generation.current) setSimulationLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshSimulation()
    const timer = window.setInterval(() => void refreshSimulation(), STATUS_POLL_MS)
    return () => window.clearInterval(timer)
  }, [refreshSimulation])

  // Detection: the agent reporting a new incident of the injected type. This is
  // the only transition that produces an incident id.
  const event = stream.lastEvent
  useEffect(() => {
    if (!event) return
    knownIncidents.current.add(event.incident_id)
    if (phase !== 'pending' || mode === null) return
    if (event.status !== 'detected' || event.type !== mode) return
    if (knownAtInjection.current.has(event.incident_id)) return
    setPhase('reported')
    setIncidentId(event.incident_id)
  }, [event, phase, mode])

  // Honesty on the other side: once the app reports no active fault, the window
  // in which the agent could still have detected it has closed. Say so instead
  // of showing a pending state that will never resolve.
  useEffect(() => {
    if (phase !== 'pending') return
    if (simulation === null || simulation.mode !== null) return
    setPhase('undetected')
  }, [phase, simulation])

  const inject = useCallback(async (nextMode: FaultMode, durationSeconds?: number) => {
    generation.current += 1
    knownAtInjection.current = new Set(knownIncidents.current)
    setError(null)
    setIncidentId(null)
    setMode(nextMode)
    setPhase('injecting')
    try {
      const status = await injectFault(nextMode, durationSeconds)
      // Seed the status with what the route just returned: it proves the fault
      // is active, so the "no active fault" transition cannot fire early.
      setSimulation(status)
      setSimulationError(null)
      setSimulationLoading(false)
      setInjectedAt(Date.now())
      setPhase('pending')
      void refreshSimulation()
    } catch (failure: unknown) {
      setPhase('idle')
      setError(describeError(failure))
    }
  }, [refreshSimulation])

  const reset = useCallback(async () => {
    generation.current += 1
    setError(null)
    try {
      const status = await resetSimulation()
      setSimulation(status)
      setSimulationError(null)
      setSimulationLoading(false)
      setPhase('idle')
      setMode(null)
      setIncidentId(null)
      setInjectedAt(null)
      void refreshSimulation()
    } catch (failure: unknown) {
      setSimulationError(describeError(failure))
    }
  }, [refreshSimulation])

  return {
    phase,
    mode,
    injectedAt,
    incidentId,
    error,
    simulation,
    simulationError,
    simulationLoading,
    inject,
    reset,
  }
}
