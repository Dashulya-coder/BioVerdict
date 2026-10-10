import { Badge } from '../../ui/Badge'
import { Meter } from '../../ui/Meter'
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
  supported: { label: 'Supported', tone: 'positive', meter: 'positive', border: 'border-rule' },
  weak: { label: 'Weak', tone: 'assumption', meter: 'assumption', border: 'border-assumption/40' },
  missing: {
    label: 'Missing',
    tone: 'error',
    meter: 'danger',
    border: 'border-danger/60 border-dashed',
  },
} as const

/**
 * The five links from the molecule to the patient. A missing link is drawn dashed and named:
 * absence of evidence must not look like a reassuring result.
 */
export function TranslationChain({ report }: { report: Report }) {
  const chain = report.translation_chain_probability
  return (
    <section aria-labelledby="chain" className="mt-10">
      <h2 id="chain" className="text-xl font-semibold tracking-tight">
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
            <li
              key={item.link}
              className={`relative rounded-lg border bg-surface p-4 ${look.border}`}
            >
              {index > 0 ? (
                <span
                  aria-hidden="true"
                  className="absolute top-8 -left-3 hidden h-px w-3 bg-control md:block"
                />
              ) : null}
              <p className="font-mono text-[11px] text-muted">Link {(index + 1).toString()}</p>
              <p className="mt-1 text-sm font-semibold">{names[item.link] ?? item.link}</p>
              <p className="mt-4 flex flex-wrap items-center justify-between gap-2">
                <Badge tone={look.tone}>{look.label}</Badge>
                <span className="figure text-lg">
                  {item.confidence === null ? 'no claim' : percent(item.confidence)}
                </span>
              </p>
              <p className="mt-3">
                <Meter value={item.confidence} tone={look.meter} />
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
