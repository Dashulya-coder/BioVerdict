import { Badge } from '../../ui/Badge'
import { money, months, percent } from './numbers'
import { RangeStat } from './RangeStat'
import type { Report } from './schema'

const verdictNote: Record<Report['executive']['verdict'], string> = {
  Invest: 'All conditions of the rule hold. Diligence still applies.',
  Conditional: 'Promising, but a gap or a risk below must be resolved first.',
  'Do Not Invest': 'A hard gate fired, or the evidence does not support the case.',
}

export function ExecutiveSummary({ report }: { report: Report }) {
  const { executive, gates, translation_chain_probability: chain } = report
  const fired = gates.filter((gate) => gate.fired)
  return (
    <section aria-labelledby="executive" className="border-y border-rule py-8">
      <h2 id="executive" className="sr-only">
        Executive verdict
      </h2>
      <div className="flex flex-wrap items-end gap-x-10 gap-y-4">
        <div>
          <p className="text-xs text-muted">Verdict</p>
          <p className="font-editorial text-4xl">{executive.verdict}</p>
          <p className="mt-2 max-w-sm text-sm text-muted">{verdictNote[executive.verdict]}</p>
        </div>
        <dl className="grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-3">
          <div className="border-l border-rule pl-4">
            <dt className="text-xs text-muted">Confidence in the claims</dt>
            <dd className="font-editorial text-2xl">{percent(executive.confidence)}</dd>
          </div>
          <div className="border-l border-rule pl-4">
            <dt className="text-xs text-muted">Translation chain</dt>
            <dd className="font-editorial text-2xl">{chain === null ? 'n/a' : percent(chain)}</dd>
          </div>
          <div className="border-l border-rule pl-4">
            <dt className="text-xs text-muted">Gates fired</dt>
            <dd className="font-editorial text-2xl">{fired.length.toString()}</dd>
            <dd className="text-xs text-muted">{fired.map((gate) => gate.gate_id).join(', ')}</dd>
          </div>
        </dl>
      </div>
      <dl className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <RangeStat
          label="Probability of success"
          range={executive.pos}
          format={percent}
          missing="Not computed: the bundle names no clinical stage."
        />
        <RangeStat
          label="rNPV"
          range={executive.rnpv}
          format={money}
          missing="Not computed: the market could not be sized. Invest needs it."
        />
        <RangeStat
          label="Capital to approval"
          range={executive.capital}
          format={money}
          missing="Not computed."
        />
        <RangeStat
          label="Time to next milestone"
          range={executive.months_to_milestone}
          format={months}
          missing="Not computed."
        />
      </dl>
      <div className="mt-8 grid gap-8 md:grid-cols-2">
        <div>
          <h3 className="text-sm font-medium">Top risks</h3>
          {executive.top_risks.length ? (
            <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-6">
              {executive.top_risks.map((risk) => (
                <li key={risk}>{risk}</li>
              ))}
            </ol>
          ) : (
            <p className="mt-3 text-sm text-muted">No risk was ranked.</p>
          )}
        </div>
        <div>
          <h3 className="text-sm font-medium">What would change our mind</h3>
          {executive.what_would_change_our_mind.length ? (
            <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6">
              {executive.what_would_change_our_mind.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-muted">Nothing is close to flipping the verdict.</p>
          )}
        </div>
      </div>
      {report.assumptions.length ? (
        <div className="mt-8">
          <Badge tone="assumption">Assumptions</Badge>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted">
            {report.assumptions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}
