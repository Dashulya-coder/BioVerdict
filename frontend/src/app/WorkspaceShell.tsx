import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { Badge } from '../ui/Badge'
import { Sidebar } from './Sidebar'
import { apiMode, originLabels } from './copy'
import { formatDate } from './format'
import type { PreparedAnalysis, RunSummary, Screen } from './models'

const titles: Record<Screen, string> = {
  new: 'New analysis',
  resolved: 'Resolved input',
  evidence: 'Evidence explorer',
  sources: 'Sources',
  compare: 'Compare runs',
  report: 'Report',
  trace: 'Trace and cost',
}

export function WorkspaceShell({
  screen,
  cutoff,
  analysis,
  run,
  children,
}: {
  screen: Screen
  cutoff: string
  analysis: PreparedAnalysis | null
  /** The run's status as the API reports it; `null` for the snapshot and before it answers. */
  run: RunSummary | null
  children: ReactNode
}) {
  const main = useRef<HTMLElement>(null)
  useEffect(() => {
    window.scrollTo(0, 0)
    main.current?.focus({ preventScroll: true })
  }, [screen])
  return (
    <div className="min-h-dvh lg:pl-56">
      <a
        href="#workspace"
        onClick={(event) => {
          event.preventDefault()
          main.current?.focus()
        }}
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:bg-accent focus:px-4 focus:py-3 focus:text-sidebar"
      >
        Skip to workspace
      </a>
      <Sidebar screen={screen} />
      <header className="flex min-h-16 flex-wrap items-center justify-between gap-3 border-b border-rule px-6 py-4 lg:px-10">
        <p className="text-sm text-muted">
          Workspace <span className="mx-3 text-rule">/</span>
          <span className="text-ink">{titles[screen]}</span>
        </p>
        <div className="flex items-center gap-4">
          <Badge tone="fact">
            {analysis ? originLabels[analysis.origin] : apiMode ? 'API' : originLabels.demo}
          </Badge>
          {run ? (
            <span>
              <span className="sr-only">Run status: </span>
              {run.status === 'done' ? (
                <Badge tone="fact">Verdict: {run.verdict ?? 'none'}</Badge>
              ) : run.status === 'failed' ? (
                <Badge tone="error">Run failed</Badge>
              ) : (
                <Badge tone="assumption">Reasoning…</Badge>
              )}
            </span>
          ) : null}
          {analysis?.runId ? (
            <span className="font-mono text-xs text-muted" title="Run id">
              {analysis.runId}
            </span>
          ) : null}
          <span className="font-mono text-xs text-muted">{formatDate(cutoff)}</span>
        </div>
      </header>
      <main
        id="workspace"
        ref={main}
        tabIndex={-1}
        className="mx-auto max-w-[1600px] p-6 focus-visible:outline-none lg:p-10"
      >
        {children}
      </main>
    </div>
  )
}
