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
    <div className="mt-4">
      <div
        role="img"
        aria-label={`Weight against ${module.unfavourable.toFixed(2)}, weight for ${module.favourable.toFixed(2)}`}
        className="flex h-2 gap-0.5 overflow-hidden rounded-full"
      >
        <span className="rounded-full bg-danger" style={{ width: `${against.toString()}%` }} />
        <span className="flex-1 rounded-full bg-positive" />
      </div>
      <p className="mt-2 flex justify-between font-mono text-[11px] text-muted">
        <span>against {module.unfavourable.toFixed(2)}</span>
        <span className="text-ink">balance {signed(module.balance)}</span>
        <span>for {module.favourable.toFixed(2)}</span>
      </p>
    </div>
  )
}

interface Pulled {
  claim: ReportClaim
  pull: number | undefined
}

function PullLabel({ claim, pull }: Pulled) {
  const text =
    pull === undefined
      ? claim.badge === 'unknown'
        ? 'gap'
        : 'no pull'
      : `${signed(pull)} ${pull < 0 ? 'against' : 'for'}`
  return <span className="font-mono text-[11px] text-muted">{text}</span>
}

/** One side of the scale: the claims that pull that way, strongest first. */
function Side({ title, marker, items }: { title: string; marker: string; items: Pulled[] }) {
  return (
    <div>
      <h4 className="flex items-center gap-2 text-sm font-medium">
        <span aria-hidden="true" className={`size-1.5 ${marker}`} />
        {title}
        <span className="font-normal text-muted">{items.length.toString()}</span>
      </h4>
      {items.length ? (
        <ul className="mt-3 space-y-2">
          {items.map((item) => (
            <li key={item.claim.id}>
              <PullLabel {...item} />
              <ul className="mt-1">
                <ClaimRow claim={item.claim} />
              </ul>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-muted">No claim pulls this way.</p>
      )}
    </div>
  )
}

function ModuleDetail({ module, claims }: { module: ReportModule; claims: ReportClaim[] }) {
  const pulls = new Map(module.drivers.map((driver) => [driver.claim_id, driver.contribution]))
  const items = claims.map((claim) => ({ claim, pull: pulls.get(claim.id) }))
  const byPull = (a: Pulled, b: Pulled) => Math.abs(b.pull ?? 0) - Math.abs(a.pull ?? 0)
  const against = items.filter((item) => (item.pull ?? 0) < 0).sort(byPull)
  const inFavour = items.filter((item) => (item.pull ?? 0) > 0).sort(byPull)
  const rest = items.filter((item) => (item.pull ?? 0) === 0)
  return (
    <div className="panel p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="text-base font-semibold">{module.question}</h3>
          <p className="mt-1 text-sm leading-6 text-muted">{module.headline}</p>
        </div>
        <Badge tone={answerTones[module.answer]}>{answerLabels[module.answer]}</Badge>
      </div>
      <BalanceBar module={module} />
      <p className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        <span>{plural(module.claim_ids.length, 'claim')}</span>
        <span>{plural(module.evidence_count, 'evidence item')}</span>
        <span>{plural(module.unknown_count, 'open gap')}</span>
        {module.gates.map((gate) => (
          <span key={gate} className="text-ink">
            Gate {gate} fired
          </span>
        ))}
      </p>
      {claims.length ? (
        <>
          <div className="mt-6 grid gap-6 border-t border-rule pt-5 xl:grid-cols-2">
            <Side title="Pulls against" marker="bg-danger" items={against} />
            <Side title="Pulls for" marker="bg-positive" items={inFavour} />
          </div>
          {rest.length ? (
            <details className="mt-6 border-t border-rule pt-4">
              <summary className="cursor-pointer text-sm text-muted">
                {plural(rest.length, 'claim')} with no pull: context and open gaps
              </summary>
              <ul className="mt-3 space-y-2">
                {rest.map((item) => (
                  <li key={item.claim.id}>
                    <PullLabel {...item} />
                    <ul className="mt-1">
                      <ClaimRow claim={item.claim} />
                    </ul>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
          <p className="mt-5 text-xs leading-5 text-muted">
            The number above a claim is its pull on this module: what it means for an investor times
            how likely the evidence makes it. Open a claim to read the verbatim quote and follow the
            link to its source.
          </p>
        </>
      ) : (
        <p className="mt-5 text-sm text-muted">No claim was written for this module.</p>
      )}
    </div>
  )
}

/** The six modules: pick one on the left, read its answer and both sides of its scale. */
export function ModuleScorecard({
  report,
  selected,
  onSelect,
}: {
  report: Report
  /** The module shown; `null` shows the first. */
  selected: string | null
  onSelect: (module: string) => void
}) {
  if (report.modules.length === 0) return null
  const claims = new Map(
    report.sections.flatMap((section) => section.claims).map((claim) => [claim.id, claim]),
  )
  const shown = report.modules.find((module) => module.module === selected) ?? report.modules[0]
  if (!shown) return null
  return (
    <section aria-labelledby="modules" className="mt-10">
      <h2 id="modules" className="text-xl font-semibold tracking-tight">
        Six modules, six answers
      </h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
        Code computes each answer from the module's claims: what a claim means for an investor,
        weighted by the confidence its evidence gives it. A fired kill gate decides a module; a soft
        gate caps it at Mixed. New evidence moves an answer only through the claims it touches.
      </p>
      <div className="mt-5 grid gap-4 lg:grid-cols-[17rem_minmax(0,1fr)]">
        <ul className="flex gap-1 overflow-x-auto lg:flex-col lg:overflow-visible">
          {report.modules.map((module) => {
            const current = module.module === shown.module
            return (
              <li key={module.module} className="shrink-0">
                <button
                  type="button"
                  aria-pressed={current}
                  onClick={() => {
                    onSelect(module.module)
                  }}
                  className={`w-full rounded-md px-3 py-2.5 text-left transition-colors ${current ? 'bg-selected shadow-[inset_2px_0_0_var(--color-accent)]' : 'hover:bg-surface'}`}
                >
                  <span className={`block text-sm ${current ? 'font-medium' : ''}`}>
                    {module.title}
                  </span>
                  <span className="mt-0.5 block text-xs text-muted">
                    {answerLabels[module.answer]} · {signed(module.balance)}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
        <ModuleDetail
          key={shown.module}
          module={shown}
          claims={shown.claim_ids.flatMap((id) => claims.get(id) ?? [])}
        />
      </div>
    </section>
  )
}
