import { request } from '../../app/api-client'
import { fullTraceSchema } from './schema'
import type { FullTrace } from './schema'

export function fetchTrace(runId: string, signal: AbortSignal): Promise<FullTrace> {
  return request(`/runs/${runId}/trace`, fullTraceSchema, signal)
}
