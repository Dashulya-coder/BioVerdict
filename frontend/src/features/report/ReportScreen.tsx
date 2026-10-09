import { Button } from '../../ui/Button'
import { PageHeading } from '../../ui/PageHeading'
import { navigate } from '../../app/useScreen'
import { ClaimList } from './ClaimList'
import { ExecutiveSummary } from './ExecutiveSummary'
import { TranslationChain } from './TranslationChain'
import { UnknownFacts } from './UnknownFacts'
import { useReport } from './useReport'
import type { PreparedAnalysis } from '../../app/models'

export function ReportScreen({ analysis }: { analysis: PreparedAnalysis }) {
  return (
    <section>
      <PageHeading
        eyebrow="Underwriting report"
        title="Verdict and the reasons behind it"
        description="Code decides the verdict from grounded claims. Every number marked Modeled follows from stated assumptions."
      />
      {analysis.runId ? (
        <LoadedReport runId={analysis.runId} />
      ) : (
        <div className="max-w-2xl border border-rule bg-surface p-6 text-sm leading-7">
          <p>The prepared snapshot has no report: it holds evidence only.</p>
          <p className="mt-2 text-muted">Start the API and run an analysis to see a verdict.</p>
          <div className="mt-4">
            <Button
              variant="secondary"
              onClick={() => {
                navigate('new')
              }}
            >
              New analysis
            </Button>
          </div>
        </div>
      )}
    </section>
  )
}

function LoadedReport({ runId }: { runId: string }) {
  const state = useReport(runId)
  if (state.kind === 'loading')
    return (
      <p role="status" className="text-sm text-muted">
        {state.progress}…
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
      <ExecutiveSummary report={state.report} />
      <TranslationChain report={state.report} />
      <UnknownFacts report={state.report} />
      <ClaimList report={state.report} />
    </>
  )
}
