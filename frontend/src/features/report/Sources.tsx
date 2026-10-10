import type { Report } from './schema'
import { showClaim } from './showClaim'

/** The claims the decision rests on: key claims, the claims behind risks and gates, and the
 * claims the written case cites. */
function majorClaims(report: Report): Set<string> {
  const ids = new Set<string>()
  for (const section of report.sections)
    for (const claim of section.claims) if (claim.critical) ids.add(claim.id)
  for (const risk of report.executive.top_risk_claims) for (const id of risk) ids.add(id)
  for (const gate of report.gates) if (gate.fired) for (const id of gate.claim_ids) ids.add(id)
  for (const thesis of report.theses)
    for (const sentence of thesis.sentences) for (const id of sentence.claim_ids) ids.add(id)
  return ids
}

/** The records the major claims quote, most cited first, each with the claims that quote it. */
export function Sources({ report }: { report: Report }) {
  const major = majorClaims(report)
  const sources = report.sources
    .map((source) => ({ ...source, major: source.claim_ids.filter((id) => major.has(id)) }))
    .filter((source) => source.major.length)
    .sort((a, b) => b.major.length - a.major.length || a.id.localeCompare(b.id))
  return (
    <section aria-labelledby="sources" className="mt-10">
      <h2 id="sources" className="text-xl font-semibold tracking-tight">
        Sources supporting major claims
      </h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
        The records quoted by the key claims, the claims behind the risks and gates, and the claims
        the written case cites. Every claim opens onto its verbatim quotation.
      </p>
      {sources.length ? (
        <ul className="mt-5 max-w-4xl divide-y divide-rule border-y border-rule">
          {sources.map((source) => (
            <li key={source.id} className="py-3 text-sm leading-6">
              <a href={source.url} target="_blank" rel="noreferrer" className="underline">
                {source.source}
              </a>
              <span className="ml-2 text-xs text-muted">
                {source.id} · {source.level.replaceAll('_', ' ')}
                {source.published_at ? ` · ${source.published_at}` : ''}
              </span>
              <span className="ml-2 text-xs text-muted">quoted by</span>
              {source.major.map((claimId) => (
                <button
                  key={claimId}
                  type="button"
                  onClick={() => {
                    showClaim(claimId)
                  }}
                  className="ml-2 font-mono text-xs text-accent underline"
                >
                  {claimId}
                </button>
              ))}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 max-w-2xl text-sm text-muted">
          No major claim of this run quotes a source.
        </p>
      )}
    </section>
  )
}
