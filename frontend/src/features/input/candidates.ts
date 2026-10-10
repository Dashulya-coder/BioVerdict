import { z } from 'zod'
import type { Evidence, PreparedAnalysis } from '../../app/models'

const designSchema = z.object({
  phases: z.array(z.string()).default([]),
  armGroups: z.array(z.object({ label: z.string(), type: z.string() })),
  interventions: z.array(
    z.object({
      name: z.string(),
      type: z.string(),
      armGroupLabels: z.array(z.string()).default([]),
    }),
  ),
})

export interface Candidate {
  name: string
  records: { evidenceId: string; study: string; url: string; phases: string[] }[]
}

export function isLandscape(analysis: PreparedAnalysis): boolean {
  return analysis.input.asset.trim() === ''
}

/** Only explicit experimental drug arms; never infer an asset from a paper or study title. */
export function candidates(evidence: readonly Evidence[]): Candidate[] {
  const found = new Map<string, Candidate>()
  for (const item of evidence) {
    if (item.source_family !== 'registry' || item.locator?.type !== 'nct') continue
    let raw: unknown
    try {
      raw = JSON.parse(item.excerpt) as unknown
    } catch {
      continue
    }
    const parsed = designSchema.safeParse(raw)
    if (!parsed.success) continue
    const design = parsed.data
    const experimental = new Set(
      design.armGroups.filter((arm) => arm.type === 'EXPERIMENTAL').map((arm) => arm.label),
    )
    for (const intervention of design.interventions) {
      const name = intervention.name.trim()
      if (
        !name ||
        !['DRUG', 'BIOLOGICAL'].includes(intervention.type) ||
        /\bplacebo\b/i.test(name) ||
        !intervention.armGroupLabels.some((label) => experimental.has(label))
      )
        continue
      const key = name.toLocaleLowerCase('en-US')
      const candidate = found.get(key) ?? { name, records: [] }
      if (!candidate.records.some((record) => record.study === item.locator?.value))
        candidate.records.push({
          evidenceId: item.id,
          study: item.locator.value,
          url: item.url,
          phases: design.phases,
        })
      found.set(key, candidate)
    }
  }
  return [...found.values()].sort((a, b) => a.name.localeCompare(b.name))
}
