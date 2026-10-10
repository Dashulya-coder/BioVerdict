import { Badge } from '../../ui/Badge'
import type { Report } from './schema'
import { showClaim } from './showClaim'
import { thesisTitles } from './thesisTitles'

/** The written theses: a model's synthesis over the claims, each sentence leading to its claims. */
export function Theses({ report }: { report: Report }) {
  return (
    <section aria-labelledby="theses" className="mt-10">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="theses" className="font-editorial text-2xl">
          The underwriting case
        </h2>
        <Badge tone="assumption">AI inference</Badge>
      </div>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
        Written by a model over the claims, after code computed the verdict. A sentence is kept only
        if it cites claims of this run and every number in it comes from those claims or from the
        figures code computed. The verdict does not depend on this text.
      </p>
      {report.theses.length ? (
        <div className="mt-5 grid max-w-4xl gap-6 md:grid-cols-2">
          {report.theses.map((thesis) => (
            <article
              key={thesis.kind}
              id={`thesis-${thesis.kind}`}
              aria-label={thesisTitles[thesis.kind]}
              className="border border-rule bg-surface p-5"
            >
              <h3 className="font-editorial text-lg">{thesisTitles[thesis.kind]}</h3>
              <ul className="mt-3 space-y-3">
                {thesis.sentences.map((sentence) => (
                  <li key={sentence.text} className="text-sm leading-6">
                    {sentence.text}
                    {sentence.claim_ids.map((claimId) => (
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
            </article>
          ))}
        </div>
      ) : (
        <p className="mt-4 max-w-2xl text-sm text-muted">
          No written case for this run: the synthesis step did not finish, or the run is older than
          it.
        </p>
      )}
    </section>
  )
}
