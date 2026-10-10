import { verdictLook } from '../../app/verdict'
import { Badge } from '../../ui/Badge'
import { Meter } from '../../ui/Meter'
import { money, months, percent } from './numbers'
import { RangeStat } from './RangeStat'
import type { Report } from './schema'
import { showClaim } from './showClaim'

const verdictNote: Record<Report['executive']['verdict'], string> = {
  Invest: 'All conditions of the rule hold. Diligence still applies.',
  Conditional: 'Promising, but a gap or a risk below must be resolved first.',
  'Do Not Invest': 'A hard gate fired, or the evidence does not support the case.',
}

export function ExecutiveSummary({ report }: { report: Report }) {
  const { executive, gates, translation_chain_probability: chain } = report
  const fired = gates.filter((gate) => gate.fired)
  const look = verdictLook(executive.verdict)
  return (
    <section aria-labelledby="executive">
      <h2 id="executive" className="sr-only">
        Executive verdict
      </h2>
      <div className="relative overflow-hidden panel">
        <span aria-hidden="true" className={`absolute inset-y-0 left-0 w-1 ${look.fill}`} />
        <div className="grid gap-8 p-6 sm:p-8 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] xl:items-center">
          <div>
            <p className="text-xs font-medium tracking-wide text-muted uppercase">Verdict</p>
            <p
              className={`mt-2 font-editorial text-5xl leading-none font-medium tracking-tight sm:text-6xl ${look.text}`}
            >
              {executive.verdict}
            </p>
            <p className="mt-4 max-w-sm text-sm leading-6 text-muted">
              {verdictNote[executive.verdict]}
            </p>
          </div>
          <dl className="grid gap-4 sm:grid-cols-3">
            <div className="rounded-md bg-raised p-4">
              <dt className="text-xs text-muted">Confidence in the claims</dt>
              <dd className="mt-1 figure text-3xl">{percent(executive.confidence)}</dd>
              <dd className="mt-3">
                <Meter value={executive.confidence} />
              </dd>
            </div>
            <div className="rounded-md bg-raised p-4">
              <dt className="text-xs text-muted">Translation chain</dt>
              <dd className="mt-1 figure text-3xl">{chain === null ? 'n/a' : percent(chain)}</dd>
              <dd className="mt-3">
                <Meter value={chain} tone="assumption" />
              </dd>
            </div>
            <div className="rounded-md bg-raised p-4">
              <dt className="text-xs text-muted">Gates fired</dt>
              <dd className="mt-1 figure text-3xl">{fired.length.toString()}</dd>
              <dd className="mt-2 flex min-h-5 flex-wrap gap-1 text-xs text-muted">
                {fired.map((gate) => gate.gate_id).join(', ')}
              </dd>
            </div>
          </dl>
        </div>
        <dl
          id="capital"
          className="grid gap-px border-t border-rule bg-rule sm:grid-cols-2 lg:grid-cols-5"
        >
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
            label="Capital to next milestone"
            range={executive.capital_to_milestone}
            format={money}
            missing="Not computed: the bundle names no clinical stage."
          />
          <RangeStat
            label="Capital to approval"
            range={executive.capital}
            format={money}
            missing="Not computed: the bundle names no clinical stage."
          />
          <RangeStat
            label="Time to next milestone"
            range={executive.months_to_milestone}
            format={months}
            missing="Not computed: the bundle names no clinical stage."
          />
        </dl>
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <div className="panel p-6">
          <h3 id="risks" className="flex items-center gap-2 text-sm font-semibold">
            <span aria-hidden="true" className="size-2 rounded-full bg-danger" />
            Key risks and failure modes
          </h3>
          {executive.top_risks.length ? (
            <ol className="mt-4 space-y-3 text-sm leading-6">
              {executive.top_risks.map((risk, index) => (
                <li key={risk} className="flex gap-3">
                  <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-raised figure text-[11px] text-muted">
                    {(index + 1).toString()}
                  </span>
                  <span>
                    {risk}
                    {(executive.top_risk_claims[index] ?? []).map((claimId) => (
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
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="mt-3 text-sm text-muted">No risk was ranked.</p>
          )}
        </div>
        <div className="panel p-6">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <span aria-hidden="true" className="size-2 rounded-full bg-accent" />
            What would change our mind
          </h3>
          {executive.what_would_change_our_mind.length ? (
            <ul className="mt-4 space-y-3 text-sm leading-6">
              {executive.what_would_change_our_mind.map((item) => (
                <li key={item} className="flex gap-3">
                  <span aria-hidden="true" className="mt-2.5 h-px w-3 shrink-0 bg-control" />
                  {item}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-muted">Nothing is close to flipping the verdict.</p>
          )}
        </div>
      </div>
      {report.assumptions.length ? (
        <div className="mt-4 rounded-lg border border-dashed border-assumption/30 p-5">
          <Badge tone="assumption">Assumptions</Badge>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm leading-6 text-muted">
            {report.assumptions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}
