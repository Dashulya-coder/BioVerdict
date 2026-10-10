import { PageHeading } from '../../ui/PageHeading'
import { CallTable } from './CallTable'
import { CostSummary } from './CostSummary'
import { StepCosts } from './StepCosts'
import { Timeline } from './Timeline'
import { useTrace } from './useTrace'
import type { PreparedAnalysis, RunSummary } from '../../app/models'

export function TraceScreen({
  analysis,
  status,
}: {
  analysis: PreparedAnalysis
  status: RunSummary | null
}) {
  return (
    <section>
      <PageHeading
        eyebrow="Trace and cost"
        title="What the run did and what it cost"
        description="Every step and every model call of the run, with the model that answered, its tokens, time and price."
      />
      {analysis.runId ? (
        <LoadedTrace
          runId={analysis.runId}
          running={status === null || (status.status !== 'done' && status.status !== 'failed')}
        />
      ) : (
        <p className="max-w-2xl border border-rule bg-surface p-6 text-sm leading-7 text-muted">
          The prepared snapshot has no trace. Start the API and run an analysis to see one.
        </p>
      )}
    </section>
  )
}

function LoadedTrace({ runId, running }: { runId: string; running: boolean }) {
  const state = useTrace(runId, running)
  if (state.kind === 'loading')
    return (
      <p role="status" className="text-sm text-muted">
        Loading the trace…
      </p>
    )
  if (state.kind === 'error')
    return (
      <p role="alert" className="max-w-2xl border border-danger/40 p-4 text-sm text-danger">
        {state.message}
      </p>
    )
  return (
    <>
      <CostSummary trace={state.trace} />
      <StepCosts trace={state.trace} />
      <Timeline trace={state.trace} />
      <CallTable trace={state.trace} />
    </>
  )
}
