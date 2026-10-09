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
export const evidenceLevels = [
  'human_genetics',
  'human_interventional',
  'human_observational',
  'animal_in_vivo',
  'in_vitro',
  'registry_record',
] as const
export const levelLabels: Record<(typeof evidenceLevels)[number], string> = {
  human_genetics: 'Human genetics',
  human_interventional: 'Human interventional',
  human_observational: 'Human observational',
  animal_in_vivo: 'Animal, in vivo',
  in_vitro: 'In vitro',
  registry_record: 'Registry record (no finding)',
}
export const sourceLabels: Record<SourceKind, string> = {
  peer_reviewed: 'Peer-reviewed',
  regulator: 'Regulator',
  registry: 'Registry',
  preprint: 'Preprint',
  company: 'Company',
  ai_inference: 'AI inference',
}
