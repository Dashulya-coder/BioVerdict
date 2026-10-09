import { request, wait } from '../../app/api-client'
import { runSummarySchema, traceSchema } from '../../app/schemas'
import { WorkspaceError } from '../../app/WorkspaceError'
import { reportSchema } from './schema'
import type { Report } from './schema'

const POLL_MS = 1000
const LIMIT_MS = 15 * 60 * 1000

/**
 * The report of a run, once the backend has finished reasoning and scoring it. The evidence
 * screens need only the frozen bundle; the report waits for the verdict.
 */
export async function fetchReport(
  runId: string,
  onProgress: (text: string) => void,
  signal: AbortSignal,
): Promise<Report> {
  const deadline = Date.now() + LIMIT_MS
  for (;;) {
    const run = await request(`/runs/${runId}`, runSummarySchema, signal)
    if (run.status === 'done') break
    if (run.status === 'failed') {
      const { events } = await request(`/runs/${runId}/trace`, traceSchema, signal)
      const reason = events.findLast((event) => event.status === 'failed')?.detail
      throw new WorkspaceError(`The run failed: ${reason ?? 'no reason given'}`, 'edit')
    }
    const { events } = await request(`/runs/${runId}/trace`, traceSchema, signal)
    const last = events.at(-1)
    onProgress(last ? `Working: ${last.step}` : 'Working')
    if (Date.now() > deadline)
      throw new WorkspaceError(`Run ${runId} is taking too long. Check the backend.`, 'edit')
    await wait(POLL_MS, signal)
  }
  return request(`/runs/${runId}/report`, reportSchema, signal)
}
