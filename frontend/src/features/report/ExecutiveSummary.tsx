import { Badge } from '../../ui/Badge'
import { Overview } from './Overview'
import type { Report } from './schema'
import { showClaim } from './showClaim'

const jump = 'ml-2 font-mono text-xs text-ink underline decoration-control underline-offset-4'

export function ExecutiveSummary({
  report,
  onSelectModule,
}: {
  report: Report
  onSelectModule: (module: string) => void
}) {
  const { executive } = report
  return (
    <section aria-labelledby="executive">
      <h2 id="executive" className="sr-only">
        Executive verdict
      </h2>
      <Overview report={report} onSelectModule={onSelectModule} />
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <div className="panel p-5">
          <h3 id="risks" className="text-sm font-medium">
            Key risks and failure modes
          </h3>
          {executive.top_risks.length ? (
            <ol className="mt-3 space-y-2.5 text-sm leading-6">
              {executive.top_risks.map((risk, index) => (
                <li key={risk} className="flex gap-3">
                  <span className="w-4 shrink-0 text-muted tabular-nums">
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
                        className={jump}
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
        <div className="panel p-5">
          <h3 className="text-sm font-medium">What would change our mind</h3>
          {executive.what_would_change_our_mind.length ? (
            <ul className="mt-3 list-disc space-y-2.5 pl-5 text-sm leading-6 marker:text-control">
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
        <div className="mt-4 rounded-lg border border-rule p-5">
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
