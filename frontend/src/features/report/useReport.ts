import { useEffect, useState } from 'react'
import { WorkspaceError } from '../../app/WorkspaceError'
import { fetchReport } from './api'
import type { Report } from './schema'

export type ReportState =
  | { kind: 'loading'; progress: string }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; report: Report }

/** Loads the report of `runId`; a new run id starts over. */
export function useReport(runId: string): ReportState {
  const [loaded, setLoaded] = useState<{ runId: string; state: ReportState } | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    fetchReport(
      runId,
      (progress) => {
        setLoaded({ runId, state: { kind: 'loading', progress } })
      },
      controller.signal,
    )
      .then((report) => {
        setLoaded({ runId, state: { kind: 'ready', report } })
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        const message =
          error instanceof WorkspaceError
            ? error.message
            : 'The report could not be loaded. Try again.'
        setLoaded({ runId, state: { kind: 'error', message } })
      })
    return () => {
      controller.abort()
    }
  }, [runId])
  return loaded?.runId === runId
    ? loaded.state
    : { kind: 'loading', progress: 'Loading the report' }
}
