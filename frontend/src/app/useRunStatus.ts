import { useEffect, useState } from 'react'
import { getRun } from './api-client'
import type { RunSummary } from './models'

const POLL_MS = 1000
const ended = (run: RunSummary) => run.status === 'done' || run.status === 'failed'

/**
 * The status of a run, followed until it ends. The workspace opens a run once its evidence is
 * frozen, while reasoning and scoring are still going: this is what tells the two apart.
 * `null` until the first answer, and for an analysis that is not a run of the API.
 */
export function useRunStatus(runId: string | null): RunSummary | null {
  const [run, setRun] = useState<RunSummary | null>(null)
  useEffect(() => {
    if (!runId) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    const poll = () => {
      getRun(runId, controller.signal)
        .then((found) => {
          setRun(found)
          if (!ended(found)) timer = setTimeout(poll, POLL_MS)
        })
        .catch(() => {
          // One missed answer is not the end of the run: ask again while the screen is open.
          if (!controller.signal.aborted) timer = setTimeout(poll, POLL_MS)
        })
    }
    poll()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [runId])
  return run?.run_id === runId ? run : null
}
