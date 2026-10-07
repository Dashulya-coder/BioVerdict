import { useEffect, useState } from 'react'
import { Button } from '../ui/Button'
import { PageHeading } from '../ui/PageHeading'
import { AnalysisForm } from '../features/input/AnalysisForm'
import { ResolvedInput } from '../features/input/ResolvedInput'
import { EvidenceExplorer } from '../features/evidence/EvidenceExplorer'
import { WorkspaceShell } from './WorkspaceShell'
import { DEMO_DATE } from './constants'
import { useAnalysis } from './useAnalysis'
import { navigate, useScreen } from './useScreen'
import type { AnalysisInput } from './models'

export function Workspace() {
  const [draft, setDraft] = useState<AnalysisInput>({ asset: 'Divarasib', as_of: DEMO_DATE })
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
    <WorkspaceShell screen={screen} cutoff={analysis?.input.as_of ?? DEMO_DATE}>
      {screen === 'new' ? (
        <AnalysisForm
          draft={draft}
          onChange={changeInput}
          onSubmit={submit}
          loading={state.kind === 'loading'}
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
            description="Open the prepared Divarasib demo to review its input and explore the dated evidence."
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
