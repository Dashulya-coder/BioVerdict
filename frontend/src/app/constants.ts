import type { SourceKind } from './models'

export const DEMO_DATE = '2026-10-07'
export const sourceKinds = [
  'peer_reviewed',
  'regulator',
  'registry',
  'preprint',
  'company',
  'ai_inference',
] as const
export const sourceLabels: Record<SourceKind, string> = {
  peer_reviewed: 'Peer-reviewed',
  regulator: 'Regulator',
  registry: 'Registry',
  preprint: 'Preprint',
  company: 'Company',
  ai_inference: 'AI inference',
}
