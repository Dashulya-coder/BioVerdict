import { z } from 'zod'

// The trace the API serves at /runs/{id}/trace (backend `TraceResponse`); unknown fields are ignored.
export const fullTraceSchema = z.object({
  events: z.array(
    z.object({ seq: z.number(), step: z.string(), status: z.string(), detail: z.string() }),
  ),
  llm_calls: z.array(
    z.object({
      step: z.string(),
      provider: z.string().nullable(),
      model: z.string().nullable(),
      input_tokens: z.number(),
      output_tokens: z.number(),
      cost_usd: z.number(),
      latency_ms: z.number().nullable(),
      attempts: z.number().nullable(),
      cache_hit: z.boolean(),
      failover_from: z.string().nullable(),
      error: z.string().nullable(),
    }),
  ),
  totals: z.object({
    input_tokens: z.number(),
    output_tokens: z.number(),
    cost_usd: z.number(),
    calls: z.number(),
  }),
})
export type FullTrace = z.infer<typeof fullTraceSchema>
export type TraceCall = FullTrace['llm_calls'][number]
