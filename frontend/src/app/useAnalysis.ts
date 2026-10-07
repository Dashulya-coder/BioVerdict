import { useEffect, useRef, useState } from 'react'
import { WorkspaceError } from './WorkspaceError'
import type { AnalysisInput, AnalysisState } from './models'

export function useAnalysis() {
  const [state, setState] = useState<AnalysisState>({ kind: 'idle' })
  const request = useRef(0)
  useEffect(
    () => () => {
      request.current += 1
    },
    [],
  )
  function reset() {
    request.current += 1
    setState({ kind: 'idle' })
  }
  async function prepare(input: AnalysisInput) {
    const current = ++request.current
    setState({ kind: 'loading' })
    try {
      const { prepareDemo } = await import('./demo-client')
      const analysis = prepareDemo(input)
      if (request.current === current) setState({ kind: 'ready', analysis })
    } catch (error: unknown) {
      if (request.current === current)
        setState({
          kind: 'error',
          message:
            error instanceof WorkspaceError
              ? error.message
              : 'The workspace could not load the demo. Reload this page to try again.',
          recovery: error instanceof WorkspaceError ? error.recovery : 'reload',
        })
    }
  }
  return { state, prepare, reset }
}
