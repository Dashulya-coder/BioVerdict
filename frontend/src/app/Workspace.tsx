import { useEffect, useState } from 'react'
import { Button } from '../ui/Button'
import { PageHeading } from '../ui/PageHeading'
import { AnalysisForm } from '../features/input/AnalysisForm'
import { ResolvedInput } from '../features/input/ResolvedInput'
import { EvidenceExplorer } from '../features/evidence/EvidenceExplorer'
import { CompareRuns } from '../features/compare/CompareRuns'
import { WorkspaceShell } from './WorkspaceShell'
import { apiMode, copy, latestCutoff } from './copy'
import { useAnalysis } from './useAnalysis'
import { useRunStatus } from './useRunStatus'
import { navigate, rememberRun, rememberedRun, useScreen } from './useScreen'
import type { AnalysisInput } from './models'

export function Workspace() {
  const [draft, setDraft] = useState<AnalysisInput>(() => ({
    asset: 'Divarasib',
    as_of: latestCutoff(),
  }))
  const { state, reopened: reopening, prepare, restore, reset } = useAnalysis()
  const screen = useScreen()
  useEffect(() => {
    // A reload, or a link with `?run=`, reopens that run on the screen the address names.
    const runId = apiMode ? rememberedRun() : null
    if (runId) void restore(runId)
    // Only on the first render: `restore` is a new function on every one.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => {
    if (state.kind !== 'ready') return
    rememberRun(state.analysis.runId)
    if (!reopening) navigate('resolved')
    // `reopening` only says which kind of load just finished.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state])
  const analysis = state.kind === 'ready' ? state.analysis : null
  const run = useRunStatus(analysis?.runId ?? null)
  function changeInput(input: AnalysisInput) {
    rememberRun(null)
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
      run={run}
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
          <CompareRuns analysis={analysis} status={run} />
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
      ) : reopening && state.kind === 'loading' ? (
        <p role="status" className="text-sm text-muted">
          {state.progress}
        </p>
      ) : (
        <section>
          <PageHeading
            eyebrow="Research workspace"
            title="Start with an analysis"
            description={copy.startHint}
          />
          {reopening && state.kind === 'error' ? (
            <p role="alert" className="mb-6 max-w-2xl text-sm text-danger">
              {state.message}
            </p>
          ) : null}
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
