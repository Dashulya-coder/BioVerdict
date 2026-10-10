import { useEffect, useRef, useState } from 'react'
import { addEvidence, compareRuns, listFinishedRuns } from '../../app/api-client'
import { evidenceLevels, levelLabels, sourceKinds, sourceLabels } from '../../app/constants'
import { formatDate, subjectOf } from '../../app/format'
import { addedEvidenceSchema } from '../../app/schemas'
import { WorkspaceError } from '../../app/WorkspaceError'
import { Button } from '../../ui/Button'
import { Field } from '../../ui/Field'
import { PageHeading } from '../../ui/PageHeading'
import { DiffView } from './DiffView'
import type { PreparedAnalysis, RunDiff, RunSummary } from '../../app/models'

type Result =
  | { kind: 'idle' }
  | { kind: 'working'; text: string }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; diff: RunDiff }

const emptyDocument = {
  text: '',
  url: '',
  source: '',
  source_kind: 'peer_reviewed',
  level: 'human_interventional',
  published_at: '',
}
const selectClass =
  'mt-2 min-h-11 w-full rounded-sm border border-control bg-sidebar px-3 py-2.5 text-sm'

function describe(run: RunSummary): string {
  const subject = [run.input.asset, run.input.query, run.input.mechanism, run.input.indication]
    .filter((part): part is string => typeof part === 'string' && part !== '')
    .join(' · ')
  return `${formatDate(run.as_of)} · ${subject || 'run'} · ${run.verdict ?? 'no verdict'} · ${run.run_id}`
}

export function CompareRuns({
  analysis,
  status,
}: {
  analysis: PreparedAnalysis
  /** The status of the analysed run: only a finished run has a report to compare. */
  status: RunSummary | null
}) {
  const runId = analysis.runId
  const [runs, setRuns] = useState<readonly RunSummary[]>([])
  const [against, setAgainst] = useState('')
  const [document, setDocument] = useState(emptyDocument)
  const [result, setResult] = useState<Result>({ kind: 'idle' })
  const task = useRef<AbortController | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    listFinishedRuns(controller.signal)
      .then((found) => {
        setRuns(found.filter((run) => run.run_id !== runId))
      })
      .catch(() => {
        // The list is a convenience; a failed comparison reports the problem itself.
      })
    return () => {
      controller.abort()
      task.current?.abort()
    }
  }, [runId])

  async function run(text: string, work: (signal: AbortSignal) => Promise<RunDiff>) {
    task.current?.abort()
    const controller = new AbortController()
    task.current = controller
    setResult({ kind: 'working', text })
    try {
      const diff = await work(controller.signal)
      if (!controller.signal.aborted) setResult({ kind: 'ready', diff })
    } catch (error: unknown) {
      if (!controller.signal.aborted)
        setResult({
          kind: 'error',
          message:
            error instanceof WorkspaceError
              ? error.message
              : 'The comparison could not be completed. Try again.',
        })
    }
  }

  if (!runId)
    return (
      <PageHeading
        eyebrow="04 / Compare"
        title="Compare runs"
        description="Comparing runs needs an analysis that ran on the API."
      />
    )

  const compare = () => {
    void run('Comparing the two runs.', (signal) => compareRuns(runId, against, signal))
  }
  const add = () => {
    const parsed = addedEvidenceSchema.safeParse({
      ...document,
      published_at: document.published_at || null,
    })
    if (!parsed.success) {
      setResult({
        kind: 'error',
        message: parsed.error.issues[0]?.message ?? 'Check the document fields.',
      })
      return
    }
    const today = new Date().toISOString().slice(0, 10)
    const cutoff = analysis.input.as_of > today ? analysis.input.as_of : today
    void run('Adding the document and reasoning over the new bundle again.', async (signal) => {
      const recomputed = await addEvidence(runId, [parsed.data], cutoff, signal)
      return compareRuns(recomputed, null, signal)
    })
  }
  const finished = status?.status === 'done'
  const working = result.kind === 'working' || !finished

  return (
    <>
      <PageHeading
        eyebrow="04 / Compare"
        title="Compare runs"
        description={`See what moved the report of ${subjectOf(analysis.input)}: against another run, or after adding a document. The run must have finished.`}
      />
      {finished ? null : (
        <p role="status" className="mb-8 max-w-2xl text-sm text-assumption">
          {status?.status === 'failed'
            ? 'This run failed, so it has no report to compare. Start a new analysis.'
            : 'This run is still reasoning over its evidence. Comparing and adding a document open when it has finished.'}
        </p>
      )}
      <div className="grid gap-10 xl:grid-cols-2">
        <form
          aria-label="Compare with another run"
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            compare()
          }}
        >
          <h2 className="text-sm font-medium">Against another run</h2>
          <label className="block text-sm font-medium">
            Earlier run
            <select
              aria-label="Earlier run"
              className={selectClass}
              value={against}
              disabled={working}
              onChange={(event) => {
                setAgainst(event.currentTarget.value)
              }}
            >
              <option value="">Choose a finished run…</option>
              {runs.map((item) => (
                <option key={item.run_id} value={item.run_id}>
                  {describe(item)}
                </option>
              ))}
            </select>
          </label>
          <p className="text-xs leading-5 text-muted">
            Two runs of one drug at different cutoffs show which evidence appeared in between and
            what it changed. No model is called.
          </p>
          <Button type="submit" variant="secondary" disabled={working || !against}>
            Compare
          </Button>
        </form>

        <form
          aria-label="Add a document"
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            add()
          }}
        >
          <h2 className="text-sm font-medium">After adding a document</h2>
          <div className="space-y-2">
            <label htmlFor="added-text" className="block text-sm font-medium">
              Verbatim excerpt
            </label>
            <textarea
              id="added-text"
              rows={4}
              required
              disabled={working}
              value={document.text}
              onChange={(event) => {
                setDocument({ ...document, text: event.currentTarget.value })
              }}
              className="w-full rounded-sm border border-control bg-sidebar px-3 py-2.5 text-sm"
            />
          </div>
          <Field
            id="added-url"
            label="Source address"
            type="url"
            placeholder="https://"
            required
            disabled={working}
            value={document.url}
            onChange={(event) => {
              setDocument({ ...document, url: event.currentTarget.value })
            }}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              id="added-source"
              label="Source name"
              required
              disabled={working}
              value={document.source}
              onChange={(event) => {
                setDocument({ ...document, source: event.currentTarget.value })
              }}
            />
            <Field
              id="added-date"
              label="Published"
              type="date"
              disabled={working}
              value={document.published_at}
              onChange={(event) => {
                setDocument({ ...document, published_at: event.currentTarget.value })
              }}
            />
            <label className="text-sm font-medium">
              Source type
              <select
                aria-label="Added source type"
                className={selectClass}
                disabled={working}
                value={document.source_kind}
                onChange={(event) => {
                  setDocument({ ...document, source_kind: event.currentTarget.value })
                }}
              >
                {sourceKinds
                  .filter((kind) => kind !== 'ai_inference')
                  .map((kind) => (
                    <option key={kind} value={kind}>
                      {sourceLabels[kind]}
                    </option>
                  ))}
              </select>
            </label>
            <label className="text-sm font-medium">
              Evidence level
              <select
                aria-label="Evidence level"
                className={selectClass}
                disabled={working}
                value={document.level}
                onChange={(event) => {
                  setDocument({ ...document, level: event.currentTarget.value })
                }}
              >
                {evidenceLevels.map((level) => (
                  <option key={level} value={level}>
                    {levelLabels[level]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="text-xs leading-5 text-muted">
            The system does not retrieve or check this document: its text and labels are yours, and
            it is stored as analyst-added. The original run stays as it is; a new run reasons over
            the larger bundle, which on a live API calls the model.
          </p>
          <Button type="submit" disabled={working}>
            Add and recompute
          </Button>
        </form>
      </div>

      <div className="mt-10 border-t border-rule pt-8">
        {result.kind === 'working' ? (
          <p role="status" aria-live="polite" className="text-sm text-accent">
            {result.text}
          </p>
        ) : null}
        {result.kind === 'error' ? (
          <p
            role="alert"
            className="rounded-sm border border-danger/30 bg-danger/5 p-4 text-sm leading-6 text-danger"
          >
            {result.message}
          </p>
        ) : null}
        {result.kind === 'ready' ? <DiffView diff={result.diff} /> : null}
      </div>
    </>
  )
}
