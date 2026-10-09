import { levelLabels, sourceLabels } from '../../app/constants'
import { formatDate } from '../../app/format'
import { Badge } from '../../ui/Badge'
import { percent } from './numbers'
import type { Report, ReportClaim } from './schema'

const sectionNames: Record<string, string> = {
  unmet_need: 'Unmet need',
  mechanism: 'Mechanism',
  translation: 'Translation',
  clinical: 'Clinical',
  competition: 'Competition',
  commercial: 'Commercial',
  ip_regulatory: 'IP and regulatory',
  flags: 'Flags',
}
const basisNames: Record<string, string> = {
  extracted: 'Extracted',
  derived: 'Derived',
  inferred: 'Inferred',
  modeled: 'Modeled',
  hypothesis: 'Hypothesis',
  unknown: 'Unknown',
}
const statusNotes: Record<string, string> = {
  found: '',
  conflicting: 'The sources conflict.',
  not_reported: 'The record exists but the value was never published.',
  none_found: 'The right source was searched and holds nothing.',
  not_searched: 'Not searched: this proves nothing either way.',
  error: 'A fetch failed: this proves nothing, run again.',
  incomplete: 'The search was cut short.',
}
const directionLabels = { supports: 'Supports', contradicts: 'Contradicts', neutral: 'Neutral' }

function ClaimDetail({ claim }: { claim: ReportClaim }) {
  const parts = claim.confidence_parts
  return (
    <div className="mt-4 space-y-4 border-t border-rule pt-4 text-sm">
      {parts ? (
        <p className="text-xs text-muted">
          Support {percent(parts.support)} · contradiction {percent(parts.contra)} · freshness{' '}
          {percent(parts.freshness)} · {parts.independent_groups.toString()} independent group(s).
          Confidence is computed by code from the evidence, not stated by a model.
        </p>
      ) : null}
      {claim.links.length ? (
        <ul className="space-y-3">
          {claim.links.map((link) => (
            <li key={link.evidence_id} className="border-l-2 border-accent/50 bg-raised p-3">
              <p className="text-xs text-muted">
                <span className="font-medium text-ink">{directionLabels[link.direction]}</span> ·{' '}
                <span className="font-mono">{link.evidence_id}</span> · {link.source} ·{' '}
                {sourceLabels[link.source_kind]} · {levelLabels[link.level]} ·{' '}
                {formatDate(link.published_at)}
              </p>
              <blockquote className="mt-2 text-sm leading-6">“{link.quote}”</blockquote>
              <a
                href={link.url}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-block text-xs text-accent underline"
              >
                Open the original source: {link.source}
              </a>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted">No quotation supports this claim: it is a stated gap.</p>
      )}
      {claim.depends_on.length ? (
        <p className="font-mono text-xs text-muted">Depends on {claim.depends_on.join(', ')}</p>
      ) : null}
    </div>
  )
}

function ClaimRow({ claim }: { claim: ReportClaim }) {
  return (
    <li>
      <details className="group border border-rule bg-surface p-4 open:bg-selected">
        <summary className="cursor-pointer list-none">
          <span className="flex flex-wrap items-start justify-between gap-3">
            <span className="min-w-0 flex-1 text-sm leading-6">{claim.text}</span>
            <span className="flex flex-wrap items-center gap-2">
              <Badge tone={claim.badge === 'source_fact' ? 'fact' : 'assumption'}>
                {claim.badge === 'source_fact'
                  ? 'Source fact'
                  : claim.badge === 'ai_inference'
                    ? 'AI inference'
                    : 'Unknown'}
              </Badge>
              <span className="text-sm">{percent(claim.confidence)}</span>
            </span>
          </span>
          <span className="mt-2 flex flex-wrap gap-2 text-xs text-muted">
            <span className="font-mono">{claim.id}</span>
            <span>{basisNames[claim.basis] ?? claim.basis}</span>
            {claim.critical ? <span className="text-ink">Key claim</span> : null}
            {claim.flags.map((flag) => (
              <span key={flag}>{flag}</span>
            ))}
            {claim.gate_signals.map((gate) => (
              <span key={gate}>Signals {gate}</span>
            ))}
            <span className="ml-auto text-accent group-open:hidden">Show evidence</span>
          </span>
        </summary>
        <ClaimDetail claim={claim} />
      </details>
    </li>
  )
}

/** Recommendation → claims → quotations → sources: every claim opens onto what it rests on. */
export function ClaimList({ report }: { report: Report }) {
  return (
    <section aria-labelledby="claims" className="mt-10">
      <h2 id="claims" className="font-editorial text-2xl">
        Claims and their evidence
      </h2>
      <div className="mt-5 space-y-8">
        {report.sections.map((section) => (
          <div key={section.section}>
            <h3 className="flex flex-wrap items-baseline gap-3 text-sm font-medium">
              {sectionNames[section.section] ?? section.section}
              <span className="text-xs font-normal text-muted">
                {section.status.replace('_', ' ')} · {section.claims.length.toString()} claim(s)
              </span>
            </h3>
            {statusNotes[section.status] ? (
              <p className="mt-1 text-xs text-assumption">{statusNotes[section.status]}</p>
            ) : null}
            {section.claims.length ? (
              <ul className="mt-3 space-y-2">
                {section.claims.map((claim) => (
                  <ClaimRow key={claim.id} claim={claim} />
                ))}
              </ul>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  )
}
