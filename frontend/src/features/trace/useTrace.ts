import { useEffect, useState } from 'react'
import { WorkspaceError } from '../../app/WorkspaceError'
import { fetchTrace } from './api'
import type { FullTrace } from './schema'

const POLL_MS = 2000

export type TraceState =
  { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ready'; trace: FullTrace }

/** The trace of `runId`, asked again every two seconds until `running` is false. */
export function useTrace(runId: string, running: boolean): TraceState {
  const [loaded, setLoaded] = useState<{ runId: string; state: TraceState } | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    const load = () => {
      fetchTrace(runId, controller.signal)
        .then((trace) => {
          setLoaded({ runId, state: { kind: 'ready', trace } })
          if (running) timer = setTimeout(load, POLL_MS)
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return
          const message =
            error instanceof WorkspaceError
              ? error.message
              : 'The trace could not be loaded. Try again.'
          setLoaded({ runId, state: { kind: 'error', message } })
        })
    }
    load()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [runId, running])
  return loaded?.runId === runId ? loaded.state : { kind: 'loading' }
}
