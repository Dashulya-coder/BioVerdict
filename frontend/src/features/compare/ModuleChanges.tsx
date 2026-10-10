import { levelLabels } from '../../app/constants'
import { formatDate } from '../../app/format'
import { answerLabels, answerTones, signed } from '../../app/modules'
import type { RunDiff } from '../../app/models'
import { Badge } from '../../ui/Badge'

type Change = RunDiff['modules'][number]
type Cause = Change['causes'][number]

const share = (value: number | null) => (value === null ? 'new' : value.toFixed(2))
const directions = { supports: 'supports', contradicts: 'contradicts', neutral: 'relates to' }

function CauseItem({ cause }: { cause: Cause }) {
  return (
    <li className="border-l-2 border-accent/50 bg-raised p-3">
      <p className="text-xs text-muted">
        <span className="font-mono text-accent">{cause.evidence_id}</span> · {cause.source} ·{' '}
        {levelLabels[cause.level]} · {formatDate(cause.published_at)}
      </p>
      <blockquote className="mt-2 text-sm leading-6">“{cause.quote}”</blockquote>
      <p className="mt-2 text-sm leading-6">
        <span className="font-medium">{directions[cause.direction]}</span>{' '}
        <span className="font-mono text-xs">{cause.claim_id}</span>
        {cause.claim_change === 'added' ? ' (a new claim)' : ''}: {cause.claim_text}
      </p>
      <p className="mt-1 font-mono text-xs text-muted">
        confidence {share(cause.confidence_before)} → {cause.confidence_after.toFixed(2)} · pull on
        the module {signed(cause.contribution_before ?? 0)} → {signed(cause.contribution_after)}
      </p>
      <a
        href={cause.url}
        target="_blank"
        rel="noreferrer"
        className="mt-2 inline-block text-xs text-accent underline"
      >
        Open the source: {cause.source}
      </a>
    </li>
  )
}

function ModuleRow({ change }: { change: Change }) {
  const sameAnswer = change.answer_before === change.answer_after
  return (
    <li className={`border bg-surface p-4 ${change.changed ? 'border-accent/40' : 'border-rule'}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h4 className="text-sm font-medium">{change.title}</h4>
        <p className="flex flex-wrap items-center gap-2 text-xs">
          <Badge tone={answerTones[change.answer_before]}>
            {answerLabels[change.answer_before]}
          </Badge>
          <span aria-hidden="true">→</span>
          <span className="sr-only">changed to</span>
          <Badge tone={answerTones[change.answer_after]}>{answerLabels[change.answer_after]}</Badge>
          <span className="font-mono text-muted">
            balance {signed(change.balance_before)} → {signed(change.balance_after)}
          </span>
        </p>
      </div>
      <p className="mt-2 text-sm leading-6 text-muted">
        {change.changed
          ? sameAnswer
            ? 'The answer held, but its balance moved.'
            : 'The answer changed.'
          : 'Unchanged.'}{' '}
        {change.headline_after}
      </p>
      {change.causes.length ? (
        <>
          <p className="mt-3 text-xs text-muted">Evidence that caused it:</p>
          <ul className="mt-2 space-y-2">
            {change.causes.map((cause) => (
              <CauseItem key={`${cause.claim_id}-${cause.evidence_id}`} cause={cause} />
            ))}
          </ul>
        </>
      ) : (
        <p className="mt-2 text-xs text-muted">No new evidence reached this module.</p>
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
      <h3 className="mb-1 text-sm font-medium">
        Module by module{' '}
        <span className="text-muted">
          ({moved} of {diff.modules.length} moved)
        </span>
      </h3>
      <p className="mb-4 max-w-2xl text-xs leading-5 text-muted">
        A module moves only when new evidence reaches one of its claims. Each cause below is the
        verbatim quote, the claim it was placed on and what it did to that claim.
      </p>
      <ul className="space-y-3">
        {diff.modules.map((change) => (
          <ModuleRow key={change.module} change={change} />
        ))}
      </ul>
    </section>
  )
}
