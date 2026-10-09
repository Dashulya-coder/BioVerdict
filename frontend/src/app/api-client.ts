import type { z } from 'zod'
import {
  apiErrorSchema,
  apiEvidenceListSchema,
  diffSchema,
  healthSchema,
  inputSchema,
  resolverSchema,
  runCreatedSchema,
  runListSchema,
  runSummarySchema,
  traceSchema,
} from './schemas'
import { WorkspaceError } from './WorkspaceError'
import type { AddedEvidence, AnalysisInput, PreparedAnalysis, RunDiff, RunSummary } from './models'

/** Base URL of the BioVerdict API; without it the workspace opens the prepared snapshot. */
export const apiUrl = (import.meta.env.VITE_API_URL ?? '').trim().replace(/\/+$/, '')

const POLL_MS = 500
const RUN_LIMIT_MS = 10 * 60 * 1000
const progressLabels: Record<string, string> = {
  resolve: 'Resolving the input.',
  collect: 'Collecting evidence from the sources.',
  freeze: 'Freezing the evidence bundle.',
}

function unreachable(): WorkspaceError {
  return new WorkspaceError(
    `The BioVerdict API at ${apiUrl} did not answer. Start the backend, then try again.`,
    'edit',
  )
}

export async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  signal: AbortSignal,
  body?: unknown,
): Promise<T> {
  let response: Response
  try {
    response = await fetch(
      apiUrl + path,
      body === undefined
        ? { signal }
        : {
            signal,
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify(body),
          },
    )
  } catch (error: unknown) {
    if (signal.aborted) throw error
    throw unreachable()
  }
  const payload: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    // The API explains refusals in plain words: an unknown fixture asset, a missing model key.
    const refusal = apiErrorSchema.safeParse(payload)
    throw new WorkspaceError(
      refusal.success
        ? `The API refused the request: ${refusal.data.detail}`
        : `The API answered with an error (${String(response.status)}). Try again.`,
      'edit',
    )
  }
  const parsed = schema.safeParse(payload)
  if (!parsed.success)
    throw new WorkspaceError(
      'The API answered in a shape this workspace does not understand. Check that both run the same version.',
      'edit',
    )
  return parsed.data
}

export function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms)
    signal.addEventListener(
      'abort',
      () => {
        clearTimeout(timer)
        reject(new DOMException('Aborted', 'AbortError'))
      },
      { once: true },
    )
  })
}

/**
 * Starts a run and follows it until its evidence is frozen. The input and the evidence screens
 * need nothing later; reasoning and scoring go on in the backend under the same run id.
 */
export async function runAnalysis(
  input: AnalysisInput,
  onProgress: (text: string) => void,
  signal: AbortSignal,
): Promise<PreparedAnalysis> {
  const parsed = inputSchema.safeParse(input)
  if (!parsed.success)
    throw new WorkspaceError(
      parsed.error.issues[0]?.message ?? 'Check the analysis inputs.',
      'edit',
    )
  onProgress('Contacting the API.')
  const { mode } = await request('/health', healthSchema, signal)
  const { run_id: runId } = await request('/runs', runCreatedSchema, signal, parsed.data)

  const deadline = Date.now() + RUN_LIMIT_MS
  for (;;) {
    const { events } = await request(`/runs/${runId}/trace`, traceSchema, signal)
    const failure = events.find((event) => event.step === 'run' && event.status === 'failed')
    if (failure)
      throw new WorkspaceError(`The run failed: ${failure.detail || 'no reason given'}`, 'edit')
    if (events.some((event) => event.step === 'freeze' && event.status === 'done')) break
    const label = progressLabels[events.at(-1)?.step ?? '']
    if (label) onProgress(label)
    if (Date.now() > deadline)
      throw new WorkspaceError(`Run ${runId} is taking too long. Check the backend.`, 'edit')
    await wait(POLL_MS, signal)
  }

  const [resolver, evidence] = await Promise.all([
    request(`/runs/${runId}/resolver`, resolverSchema, signal),
    request(`/runs/${runId}/evidence`, apiEvidenceListSchema, signal),
  ])
  return { origin: mode, runId, input: parsed.data, resolver, evidence }
}

/** Finished runs, newest first: what a run can be compared with. */
export async function listFinishedRuns(signal: AbortSignal): Promise<readonly RunSummary[]> {
  const runs = await request('/runs?limit=100', runListSchema, signal)
  return runs.filter((run) => run.status === 'done')
}

/** What differs in `head` compared with `base` (default: the run `head` grew from). */
export function compareRuns(
  head: string,
  base: string | null,
  signal: AbortSignal,
): Promise<RunDiff> {
  const query = base ? `?against=${encodeURIComponent(base)}` : ''
  return request(`/runs/${head}/diff${query}`, diffSchema, signal)
}

/**
 * Adds documents to a finished run and waits for the recomputed run, whose id is returned.
 * The backend reasons over the new bundle version again; on a live API that calls the model.
 */
export async function addEvidence(
  runId: string,
  evidence: readonly AddedEvidence[],
  asOf: string,
  signal: AbortSignal,
): Promise<string> {
  const body = { evidence, as_of: asOf }
  const created = await request(`/runs/${runId}/evidence`, runCreatedSchema, signal, body)
  const deadline = Date.now() + RUN_LIMIT_MS
  for (;;) {
    const run = await request(`/runs/${created.run_id}`, runSummarySchema, signal)
    if (run.status === 'done') return run.run_id
    if (run.status === 'failed') {
      const { events } = await request(`/runs/${run.run_id}/trace`, traceSchema, signal)
      const reason = events.findLast((event) => event.status === 'failed')?.detail
      throw new WorkspaceError(`The recompute failed: ${reason ?? 'no reason given'}`, 'edit')
    }
    if (Date.now() > deadline)
      throw new WorkspaceError(`Run ${run.run_id} is taking too long. Check the backend.`, 'edit')
    await wait(POLL_MS, signal)
  }
}
