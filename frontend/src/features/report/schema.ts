import { z } from 'zod'
import { sourceKinds, evidenceLevels } from '../../app/constants'
import { moduleAnswers } from '../../app/modules'

// The report the API serves at /runs/{id}/report (backend `ReportResponse`); unknown fields are ignored.
const range = z.object({ p10: z.number(), p50: z.number(), p90: z.number() })
const badge = z.enum(['source_fact', 'ai_inference', 'unknown'])
export const verdictSchema = z.enum(['Invest', 'Conditional', 'Do Not Invest'])
const link = z.object({
  evidence_id: z.string(),
  direction: z.enum(['supports', 'contradicts', 'neutral']),
  quote: z.string(),
  source: z.string(),
  url: z.string(),
  source_kind: z.enum(sourceKinds),
  level: z.enum(evidenceLevels),
  published_at: z.iso.date().nullable(),
  badge,
})
const claim = z.object({
  id: z.string(),
  section: z.string(),
  text: z.string(),
  claim_type: z.string(),
  basis: z.string(),
  badge,
  status: z.string(),
  confidence: z.number(),
  confidence_parts: z
    .object({
      support: z.number(),
      contra: z.number(),
      freshness: z.number(),
      independent_groups: z.number(),
    })
    .nullable(),
  flags: z.array(z.string()),
  chain_link: z.string().nullable(),
  gate_signals: z.array(z.string()),
  critical: z.boolean(),
  implication: z.enum(['favourable', 'unfavourable', 'neutral']).default('neutral'),
  diligence_type: z.string().nullable(),
  depends_on: z.array(z.string()),
  links: z.array(link),
})
const moduleSchema = z.object({
  module: z.string(),
  title: z.string(),
  question: z.string(),
  answer: z.enum(moduleAnswers),
  headline: z.string(),
  balance: z.number().nullable(),
  favourable: z.number(),
  unfavourable: z.number(),
  claim_ids: z.array(z.string()),
  drivers: z.array(z.object({ claim_id: z.string(), contribution: z.number() })),
  unknown_count: z.number(),
  evidence_count: z.number(),
  gates: z.array(z.string()),
})
export const reportSchema = z.object({
  executive: z.object({
    verdict: verdictSchema,
    confidence: z.number(),
    top_risks: z.array(z.string()),
    top_risk_claims: z.array(z.array(z.string())).default([]),
    what_would_change_our_mind: z.array(z.string()),
    capital: range.nullable(),
    months_to_milestone: range.nullable(),
    pos: range.nullable(),
    rnpv: range.nullable(),
  }),
  assumptions: z.array(z.string()),
  // A report stored by an older API has no module answers.
  modules: z.array(moduleSchema).default([]),
  sections: z.array(z.object({ section: z.string(), status: z.string(), claims: z.array(claim) })),
  translation_chain: z.array(
    z.object({
      link: z.string(),
      status: z.enum(['supported', 'weak', 'missing']),
      confidence: z.number().nullable(),
      claim_ids: z.array(z.string()),
    }),
  ),
  translation_chain_probability: z.number().nullable(),
  gates: z.array(
    z.object({
      gate_id: z.string(),
      kind: z.enum(['hard', 'soft']),
      fired: z.boolean(),
      claim_ids: z.array(z.string()),
      near_miss: z.string().nullable(),
    }),
  ),
  diligence_questions: z.array(
    z.object({ text: z.string(), answered_by: z.string(), value_of_information: z.number() }),
  ),
  bundle: z.object({
    evidence_count: z.number(),
    as_of: z.iso.date(),
    content_hash: z.string(),
    version: z.number(),
  }),
})
export type Report = z.infer<typeof reportSchema>
export type Range = z.infer<typeof range>
export type ReportClaim = z.infer<typeof claim>
export type ReportModule = z.infer<typeof moduleSchema>
