import { z } from 'zod'
import { DEMO_DATE, sourceKinds } from './constants'

export const inputSchema = z.object({
  asset: z.string().trim().min(1, 'Enter a drug name.'),
  as_of: z.iso.date({ error: 'Choose a valid evidence cutoff.' }),
})
export const demoInputSchema = inputSchema.refine(
  (input) => input.as_of <= DEMO_DATE,
  'This demo snapshot is available through 7 Oct 2026.',
)
const evidenceFields = {
  id: z.string().regex(/^E-\d+$/),
  source: z.string().min(1),
  source_kind: z.enum(sourceKinds),
  url: z.httpUrl(),
  excerpt: z.string().min(1),
  published_at: z.iso.date().nullable(),
  retrieved_at: z.iso.datetime({ offset: true }),
  locator: z.object({ type: z.string(), value: z.string() }).nullable().optional(),
}
const evidenceType = z.enum(['source_fact', 'ai_inference'])
export const evidenceSchema = z.object({ ...evidenceFields, type: evidenceType })
export const resolverSchema = z.object({
  indication: z.object({ name: z.string() }),
  targets: z.array(z.object({ symbol: z.string() })).min(1),
  action: z.string().nullable(),
  modality: z.string().nullable(),
  delivery: z.string().nullable(),
  tissue: z.string().nullable(),
  known_assets: z.array(z.string()),
  assumptions: z.array(z.string()),
})
export const bundleSchema = z.object({ as_of: z.iso.date(), evidence: z.array(evidenceSchema) })

// Answers of the BioVerdict API (backend `api/schemas.py`); unknown fields are ignored.
export const healthSchema = z.object({ mode: z.enum(['fixtures', 'live']) })
export const runCreatedSchema = z.object({ run_id: z.string().min(1) })
export const traceSchema = z.object({
  events: z.array(z.object({ step: z.string(), status: z.string(), detail: z.string() })),
})
/** The API calls the evidence type its `badge`. */
export const apiEvidenceListSchema = z.array(
  z
    .object({ ...evidenceFields, badge: evidenceType })
    .transform(({ badge, ...evidence }) => ({ ...evidence, type: badge })),
)
export const apiErrorSchema = z.object({ detail: z.string() })
