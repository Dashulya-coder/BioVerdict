import { useEffect, useRef, useState } from 'react'
import { apiUrl, runAnalysis } from './api-client'
import { copy } from './copy'
import { WorkspaceError } from './WorkspaceError'
import type { AnalysisInput, AnalysisState } from './models'

export function useAnalysis() {
  const [state, setState] = useState<AnalysisState>({ kind: 'idle' })
  const request = useRef(0)
  const running = useRef<AbortController | null>(null)
  function cancel() {
    request.current += 1
    running.current?.abort()
    running.current = null
  }
  useEffect(() => cancel, [])
  function reset() {
    cancel()
    setState({ kind: 'idle' })
  }
  async function prepare(input: AnalysisInput) {
    cancel()
    const current = request.current
    const controller = new AbortController()
    running.current = controller
    setState({ kind: 'loading', progress: copy.preparing })
    try {
      let analysis
      if (apiUrl) {
        analysis = await runAnalysis(
          input,
          (progress) => {
            if (request.current === current) setState({ kind: 'loading', progress })
          },
          controller.signal,
        )
      } else {
        const { prepareDemo } = await import('./demo-client')
        analysis = prepareDemo(input)
      }
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
  return { state, prepare, reset }
}
