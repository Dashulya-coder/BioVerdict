import { answerLabels, answerTones, signed } from '../../app/modules'
import { Badge } from '../../ui/Badge'
import { ClaimRow } from './ClaimList'
import type { Report, ReportClaim, ReportModule } from './schema'

const plural = (count: number, word: string) =>
  `${count.toString()} ${word}${count === 1 ? '' : 's'}`

/** Where the weight of a module lies: against on the left, for on the right. */
function BalanceBar({ module }: { module: ReportModule }) {
  const total = module.favourable + module.unfavourable
  if (module.balance === null || total === 0) return null
  const against = (module.unfavourable / total) * 100
  return (
    <div className="mt-3">
      <div
        role="img"
        aria-label={`Weight against ${module.unfavourable.toFixed(2)}, weight for ${module.favourable.toFixed(2)}`}
        className="flex h-1.5 overflow-hidden rounded-sm bg-rule"
      >
        <span className="bg-danger/70" style={{ width: `${against.toString()}%` }} />
        <span className="flex-1 bg-accent/70" />
      </div>
      <p className="mt-1 flex justify-between font-mono text-[11px] text-muted">
        <span>against {module.unfavourable.toFixed(2)}</span>
        <span>balance {signed(module.balance)}</span>
        <span>for {module.favourable.toFixed(2)}</span>
      </p>
    </div>
  )
}

function ModuleCard({ module, claims }: { module: ReportModule; claims: ReportClaim[] }) {
  const pulls = new Map(module.drivers.map((driver) => [driver.claim_id, driver.contribution]))
  // The claims that decide the answer first, strongest pull first; then the rest.
  const ordered = [...claims].sort(
    (a, b) => Math.abs(pulls.get(b.id) ?? 0) - Math.abs(pulls.get(a.id) ?? 0),
  )
  return (
    <li>
      <details className="group border border-rule bg-surface p-4 open:border-accent/40">
        <summary className="cursor-pointer list-none">
          <span className="flex flex-wrap items-start justify-between gap-3">
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium">{module.title}</span>
              <span className="block text-xs text-muted">{module.question}</span>
            </span>
            <Badge tone={answerTones[module.answer]}>{answerLabels[module.answer]}</Badge>
          </span>
          <span className="mt-3 block text-sm leading-6">{module.headline}</span>
          <BalanceBar module={module} />
          <span className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
            <span>{plural(module.claim_ids.length, 'claim')}</span>
            <span>{plural(module.evidence_count, 'evidence item')}</span>
            <span>{plural(module.unknown_count, 'open gap')}</span>
            {module.gates.map((gate) => (
              <span key={gate} className="text-danger">
                Gate {gate} fired
              </span>
            ))}
            <span className="ml-auto text-accent group-open:hidden">Show the claims behind it</span>
          </span>
        </summary>
        <div className="mt-4 border-t border-rule pt-4">
          <p className="text-xs text-muted">
            Answer → claims → quotations → sources. Open a claim to read the verbatim quote and
            follow the link to its source. The number beside a claim is its pull on this module: its
            implication for an investor times how likely the evidence makes it.
          </p>
          {ordered.length ? (
            <ul className="mt-3 space-y-2">
              {ordered.map((claim) => {
                const pull = pulls.get(claim.id)
                return (
                  <li key={claim.id} className="grid gap-2 sm:grid-cols-[5.5rem_1fr]">
                    <span
                      className={`pt-4 font-mono text-xs ${pull === undefined ? 'text-muted' : pull < 0 ? 'text-danger' : 'text-accent'}`}
                    >
                      {pull === undefined
                        ? claim.badge === 'unknown'
                          ? 'gap'
                          : 'no pull'
                        : `${signed(pull)} ${pull < 0 ? 'against' : 'for'}`}
                    </span>
                    <ul>
                      <ClaimRow claim={claim} />
                    </ul>
                  </li>
                )
              })}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-muted">No claim was written for this module.</p>
          )}
        </div>
      </details>
    </li>
  )
}

/** The six modules, each with its answer and the trail from that answer to the sources. */
export function ModuleScorecard({ report }: { report: Report }) {
  if (report.modules.length === 0) return null
  const claims = new Map(
    report.sections.flatMap((section) => section.claims).map((claim) => [claim.id, claim]),
  )
  return (
    <section aria-labelledby="modules" className="mt-10">
      <h2 id="modules" className="font-editorial text-2xl">
        Six modules, six answers
      </h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
        Code computes each answer from the module's claims: what a claim means for an investor,
        weighted by the confidence its evidence gives it. A fired kill gate decides a module; a soft
        gate caps it at Mixed. New evidence moves an answer only through the claims it touches.
      </p>
      <ul className="mt-5 grid gap-3 xl:grid-cols-2">
        {report.modules.map((module) => (
          <ModuleCard
            key={module.module}
            module={module}
            claims={module.claim_ids.flatMap((id) => claims.get(id) ?? [])}
          />
        ))}
      </ul>
    </section>
  )
}
