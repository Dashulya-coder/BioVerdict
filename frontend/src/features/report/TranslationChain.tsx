import { Badge } from '../../ui/Badge'
import { percent } from './numbers'
import type { Report } from './schema'

const names: Record<string, string> = {
  molecular_effect: 'Molecular effect',
  human_exposure: 'Human exposure',
  target_engagement: 'Target engagement',
  biological_response: 'Biological response',
  patient_benefit: 'Patient benefit',
}
const status = {
  supported: { label: 'Supported', tone: 'fact', border: 'border-accent' },
  weak: { label: 'Weak', tone: 'assumption', border: 'border-assumption' },
  missing: { label: 'Missing', tone: 'error', border: 'border-danger border-dashed' },
} as const

/**
 * The five links from the molecule to the patient. A missing link is drawn dashed and named:
 * absence of evidence must not look like a reassuring result.
 */
export function TranslationChain({ report }: { report: Report }) {
  const chain = report.translation_chain_probability
  return (
    <section aria-labelledby="chain" className="mt-10">
      <h2 id="chain" className="font-editorial text-2xl">
        Translation chain
      </h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
        From the molecule to the patient, each link needs its own evidence.
        {chain === null
          ? ''
          : ` Probability that the whole chain holds: ${percent(chain)}, the product of the links.`}
      </p>
      <ol className="mt-5 grid gap-3 md:grid-cols-5">
        {report.translation_chain.map((item, index) => {
          const look = status[item.status]
          return (
            <li key={item.link} className={`relative border-t-2 bg-surface p-4 ${look.border}`}>
              <p className="font-mono text-xs text-muted">Link {(index + 1).toString()}</p>
              <p className="mt-1 text-sm font-medium">{names[item.link] ?? item.link}</p>
              <p className="mt-3 flex flex-wrap items-center gap-2">
                <Badge tone={look.tone}>{look.label}</Badge>
                <span className="text-xs text-muted">
                  {item.confidence === null ? 'no claim' : percent(item.confidence)}
                </span>
              </p>
              <p className="mt-3 font-mono text-xs text-muted">
                {item.claim_ids.length ? item.claim_ids.join(', ') : 'No claim for this link'}
              </p>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
