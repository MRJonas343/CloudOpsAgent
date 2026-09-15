/**
 * The dashboard's single `EventSource`, opened once and shared.
 *
 * Two things are worth knowing about this stream:
 *
 * 1. The agent's bus is process-local and keeps no history, so a reconnect has
 *    missed events by definition. `reconnectEpoch` counts reconnects and pages
 *    refetch on it, which is the "clients refetch on reconnect" contract from
 *    ADR-006. The first open is not a reconnect, so it does not bump it.
 * 2. `/events` can publish the same status back to back — a resolved run emits
 *    `resolved` from `close_incident` and again when the runner finalises the
 *    record. Every frame is still delivered (the last one carries the outcome
 *    and completion time), and the toast layer is what deduplicates.
 */

import { useEffect, useRef, useState } from 'react'

import { EVENT_NAME, EVENTS_URL } from '../api/client'
import type { IncidentEvent } from '../api/types'

export type ConnectionState = 'connecting' | 'live' | 'reconnecting'

export interface IncidentStream {
  lastEvent: IncidentEvent | null
  connection: ConnectionState
  reconnectEpoch: number
}

export function useEventStream(onEvent: (event: IncidentEvent) => void): IncidentStream {
  const [lastEvent, setLastEvent] = useState<IncidentEvent | null>(null)
  const [connection, setConnection] = useState<ConnectionState>('connecting')
  const [reconnectEpoch, setReconnectEpoch] = useState(0)

  const onEventRef = useRef(onEvent)
  const openedRef = useRef(false)

  useEffect(() => {
    onEventRef.current = onEvent
  })

  useEffect(() => {
    const source = new EventSource(EVENTS_URL)

    source.onopen = () => {
      setConnection('live')
      if (openedRef.current) setReconnectEpoch((epoch) => epoch + 1)
      openedRef.current = true
    }

    source.onerror = () => {
      // The browser reconnects on its own using the `retry:` the agent sends.
      setConnection('reconnecting')
    }

    source.addEventListener(EVENT_NAME, (message) => {
      let event: IncidentEvent
      try {
        event = JSON.parse((message as MessageEvent<string>).data) as IncidentEvent
      } catch {
        console.warn('discarding malformed event frame', message)
        return
      }
      setLastEvent(event)
      onEventRef.current(event)
    })

    return () => {
      source.close()
    }
  }, [])

  return { lastEvent, connection, reconnectEpoch }
}
