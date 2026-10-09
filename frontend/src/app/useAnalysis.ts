import { useEffect, useRef, useState } from 'react'
import { apiUrl, openRun, runAnalysis } from './api-client'
import { copy } from './copy'
import { rememberedRun } from './useScreen'
import { WorkspaceError } from './WorkspaceError'
import type { AnalysisInput, AnalysisState, PreparedAnalysis } from './models'

export function useAnalysis() {
  const [state, setState] = useState<AnalysisState>({ kind: 'idle' })
  // Whether the analysis on screen is a run the address named, not one the form started.
  const [reopened, setReopened] = useState(() => apiUrl !== '' && rememberedRun() !== null)
  const request = useRef(0)
  const running = useRef<AbortController | null>(null)
  function cancel() {
    request.current += 1
    running.current?.abort()
    running.current = null
  }
  useEffect(() => cancel, [])
  function reset() {
    setReopened(false)
    cancel()
    setState({ kind: 'idle' })
  }
  async function load(
    work: (
      onProgress: (progress: string) => void,
      signal: AbortSignal,
    ) => Promise<PreparedAnalysis>,
  ) {
    cancel()
    const current = request.current
    const controller = new AbortController()
    running.current = controller
    setState({ kind: 'loading', progress: copy.preparing })
    try {
      const analysis = await work((progress) => {
        if (request.current === current) setState({ kind: 'loading', progress })
      }, controller.signal)
      if (request.current === current) setState({ kind: 'ready', analysis })
    } catch (error: unknown) {
      if (request.current === current)
        setState({
          kind: 'error',
          message: error instanceof WorkspaceError ? error.message : copy.loadFailed,
          recovery: error instanceof WorkspaceError ? error.recovery : 'reload',
        })
    }
  }
  function prepare(input: AnalysisInput) {
    setReopened(false)
    return load(async (onProgress, signal) => {
      if (apiUrl) return runAnalysis(input, onProgress, signal)
      const { prepareDemo } = await import('./demo-client')
      return prepareDemo(input)
    })
  }
  /** Reopens the run the address named when the page loaded; the snapshot has none. */
  function restore(runId: string) {
    return load((onProgress, signal) => openRun(runId, onProgress, signal))
  }
  return { state, reopened, prepare, restore, reset }
}
