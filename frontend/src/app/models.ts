import type { z } from 'zod'
import type { sourceKinds } from './constants'
import type {
  addedEvidenceSchema,
  diffSchema,
  evidenceSchema,
  inputSchema,
  resolverSchema,
  runSummarySchema,
} from './schemas'

export type SourceKind = (typeof sourceKinds)[number]
export type AnalysisInput = z.infer<typeof inputSchema>
export type Evidence = Readonly<z.infer<typeof evidenceSchema>>
export type ResolvedInput = Readonly<z.infer<typeof resolverSchema>>
/** Where an analysis came from: the prepared snapshot, or an API answering from fixtures or live. */
export type Origin = 'demo' | 'fixtures' | 'live'
export interface PreparedAnalysis {
  readonly origin: Origin
  readonly runId: string | null
  readonly input: AnalysisInput
  readonly resolver: ResolvedInput
  readonly evidence: readonly Evidence[]
}
export type RunSummary = Readonly<z.infer<typeof runSummarySchema>>
export type AddedEvidence = z.infer<typeof addedEvidenceSchema>
export type RunDiff = Readonly<z.infer<typeof diffSchema>>
export type Screen = 'new' | 'resolved' | 'evidence' | 'sources' | 'compare' | 'report'
export type AnalysisState =
  | { kind: 'idle' }
  | { kind: 'loading'; progress: string }
  | { kind: 'error'; message: string; recovery: 'edit' | 'reload' }
  | { kind: 'ready'; analysis: PreparedAnalysis }
