import { z } from 'zod'
import { request } from '../../app/api-client'

// The modeled figures the API serves at /runs/{id}/financials (backend `FinancialsResponse`).
const financialsSchema = z.object({
  tornado: z.array(z.object({ input: z.string(), at_low: z.number(), at_high: z.number() })),
  missing: z.array(z.string()),
})
export type Financials = z.infer<typeof financialsSchema>

export function fetchFinancials(runId: string, signal: AbortSignal): Promise<Financials> {
  return request(`/runs/${runId}/financials`, financialsSchema, signal)
}
