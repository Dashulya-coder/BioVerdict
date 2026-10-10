import { Button } from '../../ui/Button'
import { candidates } from './candidates'
import type { PreparedAnalysis } from '../../app/models'

export function AssetSelection({
  analysis,
  onSelect,
}: {
  analysis: PreparedAnalysis
  onSelect: (asset: string) => void
}) {
  const found = candidates(analysis.evidence)
  return (
    <section aria-labelledby="asset-selection" className="mt-8 panel p-5">
      <h2 id="asset-selection" className="text-lg font-medium">
        Choose an existing asset
      </h2>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">
        These drugs appear in experimental arms of the retrieved trials. Review the trial to confirm
        the mechanism, population and current program status. A combination may include other drugs.
        The next analysis keeps your indication and evidence cutoff.
      </p>
      {found.length ? (
        <ul className="mt-4 divide-y divide-rule">
          {found.map((candidate) => (
            <li
              key={candidate.name}
              className="flex flex-wrap items-center justify-between gap-4 py-4"
            >
              <div>
                <p className="text-sm font-medium">{candidate.name}</p>
                <ul className="mt-2 space-y-1 text-xs text-muted">
                  {candidate.records.map((record) => (
                    <li key={record.study}>
                      <a
                        className="text-accent underline"
                        href={record.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {record.study}
                      </a>
                      {' · '}
                      {record.phases.join(', ') || 'Phase not reported'}
                      {' · '}
                      {record.evidenceId}
                    </li>
                  ))}
                </ul>
              </div>
              <Button
                variant="secondary"
                onClick={() => {
                  onSelect(candidate.name)
                }}
              >
                Select {candidate.name}
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 text-sm text-assumption">
          No experimental drug names were available in these records. Older saved bundles may lack
          the trial-arm details. Review the evidence and enter a verified asset name.
        </p>
      )}
      <Button
        className="mt-4"
        variant="ghost"
        onClick={() => {
          onSelect('')
        }}
      >
        Enter an asset name
      </Button>
    </section>
  )
}
