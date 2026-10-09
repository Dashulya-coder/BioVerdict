import { z } from 'zod'
import { DEMO_DATE, evidenceLevels, sourceKinds } from './constants'

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

// Comparing runs and adding evidence (backend `DiffResponse`, `AddEvidenceRequest`).
export const runSummarySchema = z.object({
  run_id: z.string(),
  status: z.string(),
  verdict: z.string().nullable(),
  as_of: z.iso.date(),
  input: z.record(z.string(), z.unknown()),
})
export const runListSchema = z.array(runSummarySchema)
export const addedEvidenceSchema = z.object({
  text: z
    .string()
    .trim()
    .min(20, 'Paste the verbatim excerpt (at least 20 characters).')
    .max(6000, 'Paste a shorter excerpt (at most 6,000 characters).'),
  url: z.httpUrl('Give the address the excerpt was copied from.'),
  source: z.string().trim().min(1, 'Name the source.').max(200, 'Use a shorter source name.'),
  source_kind: z.enum(sourceKinds),
  level: z.enum(evidenceLevels),
  published_at: z.iso.date().nullable(),
})
const runSideSchema = z.object({
  run_id: z.string(),
  as_of: z.iso.date(),
  bundle_version: z.number(),
  evidence_count: z.number(),
  verdict: z.string(),
  confidence: z.number(),
  translation_chain_probability: z.number().nullable(),
})
const claimSnapshotSchema = z.object({
  id: z.string(),
  basis: z.string(),
  confidence: z.number(),
  gate_signals: z.array(z.string()),
})
const diffEvidenceSchema = z.object({
  id: z.string(),
  source: z.string(),
  url: z.string(),
  excerpt: z.string(),
  published_at: z.iso.date().nullable(),
  claim_ids: z.array(z.string()),
})
export const diffSchema = z.object({
  base: runSideSchema,
  head: runSideSchema,
  verdict_changed: z.boolean(),
  gates: z.array(
    z.object({ gate_id: z.string(), fired_before: z.boolean(), fired_after: z.boolean() }),
  ),
  chain: z.array(
    z.object({ link: z.string(), status_before: z.string(), status_after: z.string() }),
  ),
  evidence_added: z.array(diffEvidenceSchema),
  evidence_removed: z.array(diffEvidenceSchema),
  claims: z.array(
    z.object({
      change: z.enum(['added', 'removed', 'changed']),
      section: z.string(),
      text: z.string(),
      before: claimSnapshotSchema.nullable(),
      after: claimSnapshotSchema.nullable(),
      new_evidence_ids: z.array(z.string()),
    }),
  ),
  unchanged_claims: z.number(),
  matching: z.string(),
})
