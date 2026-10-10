import type { ReactNode } from 'react'
import { answerLabels, signed } from '../../app/modules'
import type { ModuleAnswer } from '../../app/modules'
import { verdictLook } from '../../app/verdict'
import { diligence } from './diligence'
import { money, months, percent, rangeText } from './numbers'
import type { Range, Report, ReportModule } from './schema'
import { showPart } from './showClaim'

const verdictNote: Record<Report['executive']['verdict'], string> = {
  Invest: 'All conditions of the rule hold. Diligence still applies.',
  Conditional: 'Promising, but a gap or a risk below must be resolved first.',
  'Do Not Invest': 'A hard gate fired, or the evidence does not support the case.',
}
const answerFills: Record<ModuleAnswer, string> = {
  supports: 'bg-positive',
  mixed: 'bg-assumption',
  against: 'bg-danger',
  insufficient: 'bg-control',
}
const linkNames: Record<string, string> = {
  molecular_effect: 'Molecular effect',
  human_exposure: 'Human exposure',
  target_engagement: 'Target engagement',
  biological_response: 'Biological response',
  patient_benefit: 'Patient benefit',
}
const linkLooks = {
  supported: { label: 'Supported', ring: 'border-positive' },
  weak: { label: 'Weak', ring: 'border-assumption' },
  missing: { label: 'Missing', ring: 'border-danger border-dashed' },
} as const

const RING = 2 * Math.PI * 50

function Tile({
  title,
  aside,
  className = '',
  children,
}: {
  title: string
  aside?: string
  className?: string
  children: ReactNode
}) {
  return (
    <div className={`panel p-5 ${className}`}>
      <p className="flex items-baseline justify-between gap-3 text-sm">
        <span className="font-medium">{title}</span>
        {aside ? <span className="text-xs text-muted">{aside}</span> : null}
      </p>
      {children}
    </div>
  )
}

function VerdictTile({ report }: { report: Report }) {
  const { verdict, confidence } = report.executive
  const look = verdictLook(verdict)
  return (
    <div className="flex flex-wrap items-center gap-6 panel p-6 lg:col-span-4">
      <svg viewBox="0 0 120 120" aria-hidden="true" className="size-24 shrink-0 -rotate-90">
        <circle cx="60" cy="60" r="50" fill="none" strokeWidth="9" className="stroke-rule" />
        <circle
          cx="60"
          cy="60"
          r="50"
          fill="none"
          strokeWidth="9"
          strokeDasharray={`${(confidence * RING).toFixed(1)} ${RING.toFixed(1)}`}
          className={look.stroke}
        />
      </svg>
      <div className="min-w-0 flex-1">
        <p className="text-sm text-muted">Verdict</p>
        <p className="font-editorial text-4xl leading-tight font-medium tracking-tight">
          {verdict}
        </p>
        <p className="mt-2 text-sm leading-6 text-muted">{verdictNote[verdict]}</p>
        <p className="mt-3 text-sm">
          <span className="figure">{percent(confidence)}</span>{' '}
          <span className="text-muted">Confidence in the claims</span>
        </p>
      </div>
    </div>
  )
}

function ModuleAxis({
  modules,
  onSelect,
}: {
  modules: ReportModule[]
  onSelect: (module: string) => void
}) {
  return (
    <Tile title="Six modules" aside="against · 0 · for" className="lg:col-span-5">
      <ul className="mt-3">
        {modules.map((module) => {
          const width = Math.abs(module.balance ?? 0) * 50
          const side = (module.balance ?? 0) < 0 ? { right: '50%' } : { left: '50%' }
          return (
            <li key={module.module}>
              <button
                type="button"
                onClick={() => {
                  onSelect(module.module)
                }}
                title={answerLabels[module.answer]}
                className="grid w-full grid-cols-[minmax(0,1fr)_6rem_3rem] items-center gap-3 rounded-sm py-1.5 text-left text-sm hover:bg-raised"
              >
                <span className="truncate">{module.title}</span>
                <span aria-hidden="true" className="relative block h-1.5 rounded-full bg-raised">
                  <span
                    className={`absolute inset-y-0 rounded-full ${answerFills[module.answer]}`}
                    style={{ ...side, width: `${Math.max(width, 2).toString()}%` }}
                  />
                  <span className="absolute -inset-y-1 left-1/2 w-px bg-control" />
                </span>
                <span className="text-right font-mono text-xs text-muted">
                  {signed(module.balance)}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </Tile>
  )
}

interface Modeled {
  label: string
  range: Range | null
  format: (value: number) => string
  missing: string
}

function ModeledTile({ report }: { report: Report }) {
  const { executive } = report
  const noStage = 'Not computed: the bundle names no clinical stage.'
  const rows: Modeled[] = [
    { label: 'Probability of success', range: executive.pos, format: percent, missing: noStage },
    {
      label: 'rNPV',
      range: executive.rnpv,
      format: money,
      missing: 'Not computed: the market could not be sized. Invest needs it.',
    },
    {
      label: 'Capital to next milestone',
      range: executive.capital_to_milestone,
      format: money,
      missing: noStage,
    },
    { label: 'Capital to approval', range: executive.capital, format: money, missing: noStage },
    {
      label: 'Time to next milestone',
      range: executive.months_to_milestone,
      format: months,
      missing: noStage,
    },
  ]
  // What could not be computed is said once per reason, not once per figure.
  const reasons = [...new Set(rows.filter((row) => !row.range).map((row) => row.missing))]
  return (
    <Tile title="Modeled" aside="from stated assumptions" className="lg:col-span-3">
      <dl id="capital" className="mt-3 space-y-2.5">
        {rows.map((row) =>
          row.range ? (
            <div key={row.label}>
              <dt className="text-xs text-muted">{row.label}</dt>
              <dd className="flex flex-wrap items-baseline gap-x-2">
                <span className="figure text-lg">{row.format(row.range.p50)}</span>
                <span className="text-xs text-muted">
                  P10 to P90: {rangeText(row.range, row.format)}
                </span>
              </dd>
            </div>
          ) : null,
        )}
      </dl>
      {reasons.map((reason) => (
        <p key={reason} className="mt-3 border-t border-rule pt-3 text-xs leading-5 text-muted">
          <span className="text-ink">
            {rows
              .filter((row) => !row.range && row.missing === reason)
              .map((row) => row.label)
              .join(', ')}
          </span>
          . {reason}
        </p>
      ))}
    </Tile>
  )
}

function ChainTile({ report }: { report: Report }) {
  const chain = report.translation_chain_probability
  return (
    <Tile
      title="Translation chain"
      aside={chain === null ? 'n/a' : `${percent(chain)} that the whole chain holds`}
      className="lg:col-span-7"
    >
      <ol className="mt-5 flex">
        {report.translation_chain.map((item, index) => {
          const look = linkLooks[item.status]
          return (
            <li key={item.link} className="relative flex-1 text-center">
              {index > 0 ? (
                <span
                  aria-hidden="true"
                  className="absolute top-4 right-[calc(50%+1.25rem)] left-[calc(-50%+1.25rem)] h-px bg-rule"
                />
              ) : null}
              <span
                className={`mx-auto flex size-8 items-center justify-center rounded-full border-2 figure text-[11px] ${look.ring}`}
              >
                {item.confidence === null ? '–' : (item.confidence * 100).toFixed(0)}
              </span>
              <span className="mt-2 block text-xs">{linkNames[item.link] ?? item.link}</span>
              <span className="block text-xs text-muted">{look.label}</span>
            </li>
          )
        })}
      </ol>
    </Tile>
  )
}

function GateTile({ report }: { report: Report }) {
  const fired = report.gates.filter((gate) => gate.fired)
  return (
    <Tile
      title="Gates fired"
      aside={`${fired.length.toString()} of ${report.gates.length.toString()}`}
      className="lg:col-span-5"
    >
      <ul className="mt-4 flex flex-wrap gap-1.5">
        {report.gates.map((gate) => (
          <li
            key={gate.gate_id}
            className={`flex size-8 items-center justify-center rounded-sm border font-mono text-[11px] ${gate.fired ? 'border-danger bg-danger/15 text-ink' : gate.near_miss ? 'border-assumption/60 text-muted' : 'border-rule text-muted'}`}
          >
            {gate.gate_id}
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs leading-5 text-muted">
        {fired.length
          ? `Fired: ${fired.map((gate) => gate.gate_id).join(', ')}. `
          : 'No gate fired. '}
        <button
          type="button"
          onClick={() => {
            showPart('gates')
          }}
          className="text-ink underline decoration-control underline-offset-4"
        >
          What each gate checks
        </button>
      </p>
    </Tile>
  )
}

/** How much of what was collected reached the verdict: records, claims, quotes the judge kept. */
function FlowTile({ report }: { report: Report }) {
  const claims = report.sections.flatMap((section) => section.claims)
  const links = claims.flatMap((claim) => claim.links)
  const kept = links.filter((link) => link.judged === 'judged').length
  const removed = claims.flatMap((claim) => claim.checks).filter((c) => c.check === 'entailment')
  const steps = [
    { label: 'evidence records', count: report.bundle.evidence_count },
    { label: 'claims', count: claims.length },
    { label: 'quotes read by the judge', count: kept + removed.length },
    { label: 'quotes it kept', count: kept },
  ]
  const top = Math.max(1, ...steps.map((step) => step.count))
  return (
    <Tile title="From sources to verdict" className="lg:col-span-5">
      <ol className="mt-4 space-y-2">
        {steps.map((step) => (
          <li key={step.label} className="grid grid-cols-[3rem_1fr] items-center gap-3 text-xs">
            <span className="text-right figure text-sm">{step.count.toString()}</span>
            <span>
              <span
                aria-hidden="true"
                className="block h-1.5 rounded-full bg-control"
                style={{ width: `${Math.max((step.count / top) * 100, 1).toString()}%` }}
              />
              <span className="mt-1 block text-muted">{step.label}</span>
            </span>
          </li>
        ))}
      </ol>
    </Tile>
  )
}

function QuestionTile({ report }: { report: Report }) {
  const [first, ...rest] = [...report.diligence_questions].sort(
    (a, b) => b.value_of_information - a.value_of_information,
  )
  return (
    <Tile title="The question worth most" className="lg:col-span-7">
      {first ? (
        <>
          <p className="mt-3 text-sm leading-6">{first.text}</p>
          <p className="mt-3 text-xs text-muted">
            {diligence[first.answered_by]?.label ?? 'Open question'} · value of information{' '}
            {first.value_of_information.toFixed(2)}
            {rest.length ? (
              <>
                {' · '}
                <button
                  type="button"
                  onClick={() => {
                    showPart('questions')
                  }}
                  className="text-ink underline decoration-control underline-offset-4"
                >
                  {rest.length.toString()} more
                </button>
              </>
            ) : null}
          </p>
        </>
      ) : (
        <p className="mt-3 text-sm text-muted">None was ranked.</p>
      )}
    </Tile>
  )
}

/** The report on one screen: the verdict and what it rests on, each tile leading to its part. */
export function Overview({
  report,
  onSelectModule,
}: {
  report: Report
  onSelectModule: (module: string) => void
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-12">
      <VerdictTile report={report} />
      <ModuleAxis modules={report.modules} onSelect={onSelectModule} />
      <ModeledTile report={report} />
      <ChainTile report={report} />
      <GateTile report={report} />
      <FlowTile report={report} />
      <QuestionTile report={report} />
    </div>
  )
}
