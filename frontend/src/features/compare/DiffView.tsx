import { Badge } from '../../ui/Badge'
import { formatDate } from '../../app/format'
import type { RunDiff } from '../../app/models'

type Side = RunDiff['base']
type DiffEvidence = RunDiff['evidence_added'][number]

const share = (value: number | null) => (value === null ? 'Not computed' : value.toFixed(2))
const words = (value: string) => value.replaceAll('_', ' ')
const changeLabels = { added: 'New claim', removed: 'Claim gone', changed: 'Footing changed' }
const changeTones = { added: 'fact', removed: 'error', changed: 'assumption' } as const

function EvidenceList({ title, items }: { title: string; items: readonly DiffEvidence[] }) {
  if (items.length === 0) return null
  return (
    <section aria-label={title}>
      <h3 className="mb-3 text-sm font-medium">
        {title} <span className="text-muted">({items.length})</span>
      </h3>
      <ul className="divide-y divide-rule border-y border-rule">
        {items.map((item) => (
          <li key={item.id} className="py-4">
            <p className="flex flex-wrap items-center gap-3 text-xs text-muted">
              <span className="font-mono text-accent">{item.id}</span>
              {item.source} · {formatDate(item.published_at)}
              {item.claim_ids.length ? (
                <span>quoted by {item.claim_ids.join(', ')}</span>
              ) : (
                <span>quoted by no claim</span>
              )}
            </p>
            <blockquote className="mt-2 border-l-2 border-rule pl-3 text-sm leading-6">
              {item.excerpt}
            </blockquote>
            <a href={item.url} target="_blank" rel="noreferrer" className="mt-2 block text-xs">
              {item.url}
            </a>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function DiffView({ diff }: { diff: RunDiff }) {
  const rows: [string, (side: Side) => string][] = [
    ['Verdict', (side) => side.verdict],
    ['Confidence', (side) => share(side.confidence)],
    ['Translation chain', (side) => share(side.translation_chain_probability)],
    ['Evidence items', (side) => String(side.evidence_count)],
    ['Bundle version', (side) => `v${String(side.bundle_version)}`],
    ['Evidence cutoff', (side) => formatDate(side.as_of)],
    ['Run', (side) => side.run_id],
  ]
  return (
    <div className="space-y-10">
      <section aria-label="Before and after">
        <p role="status" className="mb-4 text-sm">
          {diff.verdict_changed
            ? `The verdict changed: ${diff.base.verdict} → ${diff.head.verdict}.`
            : `The verdict stayed ${diff.head.verdict}.`}
        </p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[480px] text-left text-sm">
            <thead className="text-xs text-muted">
              <tr className="border-y border-rule">
                <th scope="col" className="py-3 pr-4 font-normal" />
                <th scope="col" className="py-3 pr-4 font-normal">
                  Before
                </th>
                <th scope="col" className="py-3 font-normal">
                  After
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {rows.map(([label, value]) => {
                const before = value(diff.base)
                const after = value(diff.head)
                return (
                  <tr key={label}>
                    <th scope="row" className="py-3 pr-4 text-xs font-normal text-muted">
                      {label}
                    </th>
                    <td className="py-3 pr-4 font-mono text-xs">{before}</td>
                    <td
                      className={`py-3 font-mono text-xs ${before === after ? '' : 'text-accent'}`}
                    >
                      {after}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      {diff.gates.length + diff.chain.length > 0 ? (
        <section aria-label="Gates and chain">
          <h3 className="mb-3 text-sm font-medium">Gates and translation chain</h3>
          <ul className="space-y-2 text-sm">
            {diff.gates.map((gate) => (
              <li key={gate.gate_id}>
                Gate <span className="font-mono">{gate.gate_id}</span>:{' '}
                {gate.fired_before ? 'fired' : 'not fired'} →{' '}
                {gate.fired_after ? 'fired' : 'not fired'}
              </li>
            ))}
            {diff.chain.map((link) => (
              <li key={link.link}>
                Chain link {words(link.link)}:{' '}
                {link.status_before === link.status_after
                  ? link.status_after
                  : `${link.status_before} → ${link.status_after}`}
                , confidence {share(link.confidence_before)} → {share(link.confidence_after)}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <EvidenceList title="Evidence only in the later run" items={diff.evidence_added} />
      <EvidenceList title="Evidence only in the earlier run" items={diff.evidence_removed} />

      <section aria-label="Claims">
        <h3 className="mb-3 text-sm font-medium">
          Claims <span className="text-muted">({diff.claims.length} differ)</span>
        </h3>
        <p className="mb-4 text-xs text-muted">
          {diff.unchanged_claims} claims are the same in both runs.
        </p>
        <ul className="divide-y divide-rule border-y border-rule">
          {diff.claims.map((claim) => (
            <li key={`${claim.change}-${claim.section}-${claim.text}`} className="py-4">
              <p className="flex flex-wrap items-center gap-3 text-xs text-muted">
                <Badge tone={changeTones[claim.change]}>{changeLabels[claim.change]}</Badge>
                {words(claim.section)}
                <span className="font-mono">
                  {claim.before ? `${claim.before.basis} ${share(claim.before.confidence)}` : '—'}
                  {' → '}
                  {claim.after ? `${claim.after.basis} ${share(claim.after.confidence)}` : '—'}
                </span>
              </p>
              <p className="mt-2 text-sm leading-6">{claim.text}</p>
              {claim.new_evidence_ids.length ? (
                <p className="mt-2 text-xs text-accent">
                  Rests on evidence the earlier run did not have:{' '}
                  {claim.new_evidence_ids.join(', ')}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      </section>

      <p className="border-t border-rule pt-4 text-xs leading-6 text-muted">
        Computed by code from the stored records of both runs, not by a model. {diff.matching}
      </p>
    </div>
  )
}
