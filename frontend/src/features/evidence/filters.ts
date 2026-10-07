import type { Evidence, SourceKind } from '../../app/models'

export interface EvidenceFilters {
  query: string
  source: string
  kind: SourceKind | ''
}
export const emptyFilters: EvidenceFilters = { query: '', source: '', kind: '' }

export function filterEvidence(
  evidence: readonly Evidence[],
  filters: EvidenceFilters,
): readonly Evidence[] {
  const query = filters.query.trim().toLowerCase()
  return evidence.filter(
    (item) =>
      (!filters.source || item.source === filters.source) &&
      (!filters.kind || item.source_kind === filters.kind) &&
      (!query ||
        [item.id, item.source, item.excerpt, item.locator?.value ?? '']
          .join(' ')
          .toLowerCase()
          .includes(query)),
  )
}
export interface SourceGroup {
  readonly first: Evidence
  readonly items: readonly Evidence[]
}
export function groupSources(evidence: readonly Evidence[]): readonly SourceGroup[] {
  const groups = new Map<string, { first: Evidence; items: Evidence[] }>()
  for (const item of evidence) {
    const group = groups.get(item.url)
    if (group) group.items.push(item)
    else groups.set(item.url, { first: item, items: [item] })
  }
  return Array.from(groups.values())
}
