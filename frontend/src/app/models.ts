import type { z } from 'zod'
import type { sourceKinds } from './constants'
import type { evidenceSchema, inputSchema, resolverSchema } from './schemas'

export type SourceKind = (typeof sourceKinds)[number]
export type AnalysisInput = z.infer<typeof inputSchema>
export type Evidence = Readonly<z.infer<typeof evidenceSchema>>
export type ResolvedInput = Readonly<z.infer<typeof resolverSchema>>
export interface PreparedAnalysis {
  readonly input: AnalysisInput
  readonly resolver: ResolvedInput
  readonly evidence: readonly Evidence[]
}
export type Screen = 'new' | 'resolved' | 'evidence' | 'sources'
export type AnalysisState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string; recovery: 'edit' | 'reload' }
  | { kind: 'ready'; analysis: PreparedAnalysis }
