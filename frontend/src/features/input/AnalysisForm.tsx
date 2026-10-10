import { Button } from '../../ui/Button'
import { Field } from '../../ui/Field'
import { Icon } from '../../ui/Icon'
import { Badge } from '../../ui/Badge'
import { PageHeading } from '../../ui/PageHeading'
import { AnalysisSteps } from '../../app/AnalysisSteps'
import { apiMode, copy, latestCutoff } from '../../app/copy'
import type { AnalysisInput, AnalysisState } from '../../app/models'

export function AnalysisForm({
  draft,
  onChange,
  onSubmit,
  progress,
  error,
}: {
  draft: AnalysisInput
  onChange: (input: AnalysisInput) => void
  onSubmit: () => void
  /** What the run is doing now; null when nothing is running. */
  progress: string | null
  error: Extract<AnalysisState, { kind: 'error' }> | null
}) {
  const loading = progress !== null
  return (
    <>
      <PageHeading eyebrow="01 / Begin" title="New analysis" description={copy.intro} />
      <div className="grid gap-10 xl:grid-cols-[minmax(0,1fr)_280px]">
        <section aria-label="Analysis input" className="min-w-0">
          <AnalysisSteps active={0} />
          <form
            onSubmit={(event) => {
              event.preventDefault()
              onSubmit()
            }}
            className="space-y-6"
          >
            <Field
              id="asset"
              label="Asset / drug"
              placeholder="Drug name or development code"
              value={draft.asset}
              autoComplete="off"
              required={!apiMode}
              disabled={loading}
              onChange={(event) => {
                onChange({ ...draft, asset: event.currentTarget.value })
              }}
              hint={copy.assetHint}
            />
            {apiMode ? (
              <>
                <Field
                  id="indication"
                  label="Indication (optional)"
                  placeholder="For example non-small cell lung cancer"
                  value={draft.indication}
                  autoComplete="off"
                  disabled={loading}
                  onChange={(event) => {
                    onChange({ ...draft, indication: event.currentTarget.value })
                  }}
                  hint="Left empty, a known drug is analysed in its most advanced indication."
                />
                <Field
                  id="mechanism"
                  label="Mechanism / target (optional)"
                  placeholder="For example KRAS G12C inhibitor"
                  value={draft.mechanism}
                  autoComplete="off"
                  disabled={loading}
                  onChange={(event) => {
                    onChange({ ...draft, mechanism: event.currentTarget.value })
                  }}
                  hint="Give an indication with a mechanism to analyse a target without a named drug."
                />
              </>
            ) : null}
            <Field
              id="cutoff"
              label="Evidence cutoff"
              type="date"
              value={draft.as_of}
              max={latestCutoff()}
              required
              disabled={loading}
              onChange={(event) => {
                onChange({ ...draft, as_of: event.currentTarget.value })
              }}
              hint="Only evidence published by this date is shown. Undated records use their retrieval date."
            />
            {error ? (
              <div
                role="alert"
                className="rounded-sm border border-danger/30 bg-danger/5 p-4 text-sm leading-6 text-danger"
              >
                <p>{error.message}</p>
                {error.recovery === 'reload' ? (
                  <Button
                    variant="secondary"
                    className="mt-3"
                    onClick={() => {
                      window.location.reload()
                    }}
                  >
                    Reload workspace
                  </Button>
                ) : null}
              </div>
            ) : null}
            <div className="flex flex-wrap items-center justify-between gap-4 border-t border-rule pt-6">
              <div className="space-y-2">
                <Badge>{copy.runBadge}</Badge>
                <p className="text-xs text-muted">{copy.runNote}</p>
              </div>
              <Button type="submit" disabled={loading}>
                {loading ? copy.submitting : copy.submit}
                <Icon name="arrow" />
              </Button>
            </div>
            <p role="status" aria-live="polite" className="text-xs text-accent">
              {progress ?? ''}
            </p>
          </form>
          {apiMode ? null : (
            <div className="mt-8 flex flex-wrap items-center justify-between gap-4 border border-rule bg-surface px-5 py-4">
              <div>
                <p className="mb-1 text-xs text-muted">Available demo</p>
                <p className="text-sm">
                  Divarasib <span className="ml-2 font-mono text-xs text-muted">GDC-6036</span>
                </p>
              </div>
              <span className="text-xs text-muted">Snapshot / 07 Oct 2026</span>
            </div>
          )}
        </section>
        <aside className="border-t border-rule pt-6 xl:border-t-0 xl:border-l xl:pt-0 xl:pl-8">
          <h2 className="mb-6 text-sm font-medium">How this run works</h2>
          <ol className="space-y-6">
            {[
              ['Define the question', 'Choose the drug and the evidence cutoff.'],
              ['Review the assumptions', copy.reviewStep],
              [
                'Read the original evidence',
                'Keep each quotation beside its source and publication date.',
              ],
            ].map(([title, text], index) => (
              <li key={title} className="flex gap-3">
                <span className="pt-0.5 font-mono text-xs text-accent">0{index + 1}</span>
                <div>
                  <h3 className="text-sm">{title}</h3>
                  <p className="mt-2 text-xs leading-6 text-muted">{text}</p>
                </div>
              </li>
            ))}
          </ol>
          <p className="mt-8 border-t border-rule pt-5 text-xs leading-6 text-muted">
            {copy.formNote}
          </p>
        </aside>
      </div>
    </>
  )
}
