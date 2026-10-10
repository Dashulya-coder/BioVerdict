import { levelLabels } from '../../app/constants'
import { formatDate } from '../../app/format'
import { answerLabels, answerTones, signed } from '../../app/modules'
import type { RunDiff } from '../../app/models'
import { Badge } from '../../ui/Badge'
import { Meter } from '../../ui/Meter'

type Change = RunDiff['modules'][number]
type Cause = Change['causes'][number]

const share = (value: number | null) => (value === null ? 'new' : value.toFixed(2))
const directions = { supports: 'supports', contradicts: 'contradicts', neutral: 'relates to' }
const directionMarks = {
  supports: 'border-positive',
  contradicts: 'border-danger',
  neutral: 'border-control',
}

/** Where a balance from −1 (against) to +1 (for) stands on the track, in percent. */
const at = (balance: number | null) => (((balance ?? 0) + 1) / 2) * 100

/** The module's balance before (a ring) and after (a dot) on one against/for track. */
function BalanceTrack({ change }: { change: Change }) {
  const from = at(change.balance_before)
  const to = at(change.balance_after)
  return (
    <div aria-hidden="true" className="relative h-4">
      <span className="absolute inset-x-0 top-1/2 h-px bg-rule" />
      <span className="absolute top-0 bottom-0 left-1/2 w-px bg-control" />
      {change.balance_before === null || change.balance_after === null ? null : (
        <>
          <span
            className="absolute top-1/2 h-0.5 -translate-y-1/2 bg-ink"
            style={{
              left: `${Math.min(from, to).toString()}%`,
              width: `${Math.abs(to - from).toString()}%`,
            }}
          />
          <span
            className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-muted bg-canvas"
            style={{ left: `${from.toString()}%` }}
          />
          <span
            className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-ink"
            style={{ left: `${to.toString()}%` }}
          />
        </>
      )}
    </div>
  )
}

function CauseItem({ cause }: { cause: Cause }) {
  return (
    <li className={`rounded-md border-l-2 bg-raised p-4 ${directionMarks[cause.direction]}`}>
      <p className="text-xs text-muted">
        <span className="font-mono text-ink">{cause.evidence_id}</span> · {cause.source} ·{' '}
        {levelLabels[cause.level]} · {formatDate(cause.published_at)}
      </p>
      <blockquote className="mt-2 text-[15px] leading-7">“{cause.quote}”</blockquote>
      <p className="mt-3 text-sm leading-6 text-muted">
        <span className="font-medium text-ink">{directions[cause.direction]}</span>{' '}
        <span className="font-mono text-xs text-ink">{cause.claim_id}</span>
        {cause.claim_change === 'added' ? ' (a new claim)' : ''}: {cause.claim_text}
      </p>
      <div className="mt-3 grid max-w-md grid-cols-[1fr_auto_1fr] items-center gap-3">
        <Meter value={cause.confidence_before} tone="muted" />
        <span aria-hidden="true" className="text-xs text-muted">
          →
        </span>
        <Meter value={cause.confidence_after} tone="ink" />
      </div>
      <p className="mt-2 font-mono text-xs text-muted">
        confidence {share(cause.confidence_before)} → {cause.confidence_after.toFixed(2)} · pull on
        the module {signed(cause.contribution_before ?? 0)} → {signed(cause.contribution_after)}
      </p>
      <a
        href={cause.url}
        target="_blank"
        rel="noreferrer"
        className="mt-2 inline-block text-xs text-ink underline decoration-control underline-offset-4"
      >
        Open the source: {cause.source}
      </a>
    </li>
  )
}

function ModuleRow({ change }: { change: Change }) {
  const sameAnswer = change.answer_before === change.answer_after
  return (
    <li className={`panel p-5 ${change.changed ? 'shadow-[inset_2px_0_0_var(--color-ink)]' : ''}`}>
      <div className="grid items-center gap-x-6 gap-y-3 lg:grid-cols-[minmax(0,1fr)_14rem_auto]">
        <div className="min-w-0">
          <h4 className={`text-[15px] ${change.changed ? 'font-semibold' : 'text-muted'}`}>
            {change.title}
          </h4>
          <p className="mt-1 text-sm leading-6 text-muted">
            {change.changed
              ? sameAnswer
                ? 'The answer held, but its balance moved.'
                : 'The answer changed.'
              : 'Unchanged.'}{' '}
            {change.headline_after}
          </p>
        </div>
        <div>
          <BalanceTrack change={change} />
          <p className="mt-1 text-center font-mono text-[11px] text-muted">
            balance {signed(change.balance_before)} → {signed(change.balance_after)}
          </p>
        </div>
        <p className="flex flex-wrap items-center gap-2 text-xs">
          <Badge tone={answerTones[change.answer_before]}>
            {answerLabels[change.answer_before]}
          </Badge>
          <span aria-hidden="true" className="text-muted">
            →
          </span>
          <span className="sr-only">changed to</span>
          <Badge tone={answerTones[change.answer_after]}>{answerLabels[change.answer_after]}</Badge>
        </p>
      </div>
      {change.causes.length ? (
        <>
          <p className="mt-5 text-xs text-muted">Evidence that caused it:</p>
          <ul className="mt-2 space-y-2">
            {change.causes.map((cause) => (
              <CauseItem key={`${cause.claim_id}-${cause.evidence_id}`} cause={cause} />
            ))}
          </ul>
        </>
      ) : (
        <p className="mt-3 text-xs text-muted">No new evidence reached this module.</p>
      )}
    </li>
  )
}

/** Each of the six modules before and after, with the new evidence that moved it. */
export function ModuleChanges({ diff }: { diff: RunDiff }) {
  if (diff.modules.length === 0) return null
  const moved = diff.modules.filter((change) => change.changed).length
  return (
    <section aria-label="Modules">
      <h3 className="text-xl font-semibold tracking-tight">
        Module by module{' '}
        <span className="text-base font-normal text-muted">
          ({moved} of {diff.modules.length} moved)
        </span>
      </h3>
      <p className="mt-2 mb-5 max-w-2xl text-sm leading-6 text-muted">
        A module moves only when new evidence reaches one of its claims. Each cause below is the
        verbatim quote, the claim it was placed on and what it did to that claim. On the track the
        ring is the balance before and the dot the balance after: left of the middle is against,
        right is for.
      </p>
      <ul className="space-y-3">
        {diff.modules.map((change) => (
          <ModuleRow key={change.module} change={change} />
        ))}
      </ul>
    </section>
  )
}
