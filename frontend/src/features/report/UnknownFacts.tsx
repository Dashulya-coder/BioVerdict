import { Badge } from '../../ui/Badge'
import { diligence } from './diligence'
import type { Report, ReportClaim } from './schema'

const sectionNames: Record<string, string> = {
  unmet_need: 'Unmet need',
  mechanism: 'Mechanism',
  translation: 'Translation',
  clinical: 'Clinical',
  competition: 'Competition',
  commercial: 'Commercial',
  ip_regulatory: 'IP and regulatory',
}

/** What the bundle cannot tell, grouped by the kind of diligence that could. */
export function UnknownFacts({ report }: { report: Report }) {
  const unknown = report.sections.flatMap((section) =>
    section.claims.filter((claim) => claim.basis === 'unknown'),
  )
  const groups = new Map<string, ReportClaim[]>()
  for (const claim of unknown) {
    const key = claim.diligence_type ?? 'other'
    groups.set(key, [...(groups.get(key) ?? []), claim])
  }
  return (
    <section aria-labelledby="unknowns" className="mt-10">
      <h2 id="unknowns" className="font-editorial text-2xl">
        Critical unknowns
      </h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
        Public sources cannot answer these. Each names the diligence that could.
      </p>
      {unknown.length ? (
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          {[...groups].map(([type, claims]) => (
            <div key={type} className="border border-assumption/30 bg-surface p-4">
              <p className="flex flex-wrap items-center gap-2">
                <Badge tone="assumption">{diligence[type]?.label ?? 'Open question'}</Badge>
                <span className="text-xs text-muted">{diligence[type]?.how ?? ''}</span>
              </p>
              <ul className="mt-3 space-y-3 text-sm leading-6">
                {claims.map((claim) => (
                  <li key={claim.id}>
                    {claim.text}
                    <span className="mt-1 block font-mono text-xs text-muted">
                      {claim.id} · {sectionNames[claim.section] ?? claim.section}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-4 text-sm text-muted">No open question was recorded for this run.</p>
      )}
    </section>
  )
}
