import { useState } from 'react'
import { copy } from '../../app/copy'
import { formatDate, subjectOf } from '../../app/format'
import { PageHeading } from '../../ui/PageHeading'
import { Button } from '../../ui/Button'
import { Icon } from '../../ui/Icon'
import { EvidenceToolbar } from './EvidenceToolbar'
import { EvidenceTable } from './EvidenceTable'
import { EvidenceInspector } from './EvidenceInspector'
import { SourceList } from './SourceList'
import { emptyFilters, filterEvidence, groupSources } from './filters'
import type { PreparedAnalysis } from '../../app/models'

export function EvidenceExplorer({
  analysis,
  mode,
  onBack,
}: {
  analysis: PreparedAnalysis
  mode: 'evidence' | 'sources'
  onBack: () => void
}) {
  const [filters, setFilters] = useState(emptyFilters)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const evidence = filterEvidence(analysis.evidence, filters)
  const selected = evidence.find((item) => item.id === selectedId) ?? evidence[0]
  const sources = [...new Set(analysis.evidence.map((item) => item.source))].sort()
  const groups = groupSources(evidence)
  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeading
          eyebrow={mode === 'sources' ? '03 / Sources' : '03 / Evidence'}
          title={mode === 'sources' ? 'Original sources' : 'Evidence explorer'}
          description={`${copy.evidenceLead} for ${subjectOf(analysis.input)}, visible by ${formatDate(analysis.input.as_of)}. Read the source before the conclusion.`}
        />
        <Button variant="secondary" onClick={onBack}>
          <Icon name="back" />
          Review input
        </Button>
      </div>
      <EvidenceToolbar filters={filters} sources={sources} onChange={setFilters} />
      <p role="status" className="mb-4 text-xs text-muted">
        {evidence.length} of {analysis.evidence.length} evidence items · {groups.length} original
        sources
      </p>
      {selected ? (
        <div className="grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
          {mode === 'sources' ? (
            <SourceList groups={groups} selectedId={selected.id} onSelect={setSelectedId} />
          ) : (
            <EvidenceTable evidence={evidence} selectedId={selected.id} onSelect={setSelectedId} />
          )}
          <EvidenceInspector key={selected.id} evidence={selected} />
        </div>
      ) : (
        <section className="panel px-6 py-12 text-center">
          <h2 className="text-lg font-medium">
            {analysis.evidence.length ? 'No matching evidence' : 'No evidence by this cutoff'}
          </h2>
          <p className="mx-auto mt-3 max-w-md text-sm leading-7 text-muted">
            {analysis.evidence.length
              ? 'Try a different search or clear the source filters.'
              : copy.noEvidence}
          </p>
          <Button
            variant="secondary"
            className="mt-6"
            onClick={
              analysis.evidence.length
                ? () => {
                    setFilters(emptyFilters)
                  }
                : onBack
            }
          >
            {analysis.evidence.length ? 'Reset filters' : 'Review input'}
          </Button>
        </section>
      )}
    </>
  )
}
