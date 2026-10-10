import { useState } from 'react'
import { Button } from '../../ui/Button'
import { PageHeading } from '../../ui/PageHeading'
import { navigate } from '../../app/useScreen'
import { ClaimList } from './ClaimList'
import { Contents } from './Contents'
import { DiligenceQuestions } from './DiligenceQuestions'
import { ExecutiveSummary } from './ExecutiveSummary'
import { GateList } from './GateList'
import { ModuleScorecard } from './ModuleScorecard'
import { Tornado } from './Tornado'
import { showPart } from './showClaim'
import { Sources } from './Sources'
import { Theses } from './Theses'
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
        description="Code decides the verdict from grounded claims. Modeled numbers follow from stated assumptions."
      />
      {analysis.runId ? (
        <LoadedReport runId={analysis.runId} />
      ) : (
        <div className="max-w-2xl panel p-6 text-sm leading-7">
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
  const [module, setModule] = useState<string | null>(null)
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
      <ExecutiveSummary
        report={state.report}
        onSelectModule={(name) => {
          setModule(name)
          showPart('modules')
        }}
      />
      <Contents />
      <Theses report={state.report} />
      <ModuleScorecard report={state.report} selected={module} onSelect={setModule} />
      <GateList report={state.report} />
      <TranslationChain report={state.report} />
      <Tornado runId={runId} />
      <DiligenceQuestions report={state.report} />
      <UnknownFacts report={state.report} />
      <Sources report={state.report} />
      <ClaimList report={state.report} />
    </>
  )
}
