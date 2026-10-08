import { useEffect, useState } from 'react'
import { Button } from '../ui/Button'
import { PageHeading } from '../ui/PageHeading'
import { AnalysisForm } from '../features/input/AnalysisForm'
import { ResolvedInput } from '../features/input/ResolvedInput'
import { EvidenceExplorer } from '../features/evidence/EvidenceExplorer'
import { CompareRuns } from '../features/compare/CompareRuns'
import { WorkspaceShell } from './WorkspaceShell'
import { copy, latestCutoff } from './copy'
import { useAnalysis } from './useAnalysis'
import { navigate, useScreen } from './useScreen'
import type { AnalysisInput } from './models'

export function Workspace() {
  const [draft, setDraft] = useState<AnalysisInput>(() => ({
    asset: 'Divarasib',
    as_of: latestCutoff(),
  }))
  const { state, prepare, reset } = useAnalysis()
  const screen = useScreen()
  useEffect(() => {
    if (state.kind === 'ready') navigate('resolved')
  }, [state])
  const analysis = state.kind === 'ready' ? state.analysis : null
  function changeInput(input: AnalysisInput) {
    reset()
    setDraft(input)
  }
  function submit() {
    void prepare(draft)
  }
  return (
    <WorkspaceShell
      screen={screen}
      cutoff={analysis?.input.as_of ?? draft.as_of}
      analysis={analysis}
    >
      {screen === 'new' ? (
        <AnalysisForm
          draft={draft}
          onChange={changeInput}
          onSubmit={submit}
          progress={state.kind === 'loading' ? state.progress : null}
          error={state.kind === 'error' ? state : null}
        />
      ) : analysis ? (
        screen === 'resolved' ? (
          <ResolvedInput
            analysis={analysis}
            onBack={() => {
              navigate('new')
            }}
            onContinue={() => {
              navigate('evidence')
            }}
          />
        ) : screen === 'compare' ? (
          <CompareRuns analysis={analysis} />
        ) : (
          <EvidenceExplorer
            key={screen}
            analysis={analysis}
            mode={screen}
            onBack={() => {
              navigate('resolved')
            }}
          />
        )
      ) : (
        <section>
          <PageHeading
            eyebrow="Research workspace"
            title="Start with an analysis"
            description={copy.startHint}
          />
          <Button
            onClick={() => {
              navigate('new')
            }}
          >
            New analysis
          </Button>
        </section>
      )}
    </WorkspaceShell>
  )
}
