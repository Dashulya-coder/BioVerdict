import { sourceKinds, sourceLabels } from '../../app/constants'
import { Field } from '../../ui/Field'
import { Button } from '../../ui/Button'
import type { EvidenceFilters } from './filters'

export function EvidenceToolbar({
  filters,
  sources,
  onChange,
}: {
  filters: EvidenceFilters
  sources: readonly string[]
  onChange: (filters: EvidenceFilters) => void
}) {
  const selectClass =
    'mt-2 min-h-11 w-full rounded-sm border border-control bg-sidebar px-3 py-2.5 text-sm'
  return (
    <form
      role="search"
      onSubmit={(event) => {
        event.preventDefault()
      }}
      className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_190px_170px_auto] xl:items-end"
    >
      <Field
        id="evidence-search"
        label="Search evidence"
        type="search"
        value={filters.query}
        placeholder="Quote, source or identifier…"
        onChange={(event) => {
          onChange({ ...filters, query: event.currentTarget.value })
        }}
      />
      <label className="text-sm font-medium">
        Source
        <select
          aria-label="Source"
          className={selectClass}
          value={filters.source}
          onChange={(event) => {
            onChange({ ...filters, source: event.currentTarget.value })
          }}
        >
          <option value="">All sources</option>
          {sources.map((source) => (
            <option key={source}>{source}</option>
          ))}
        </select>
      </label>
      <label className="text-sm font-medium">
        Source type
        <select
          aria-label="Source type"
          className={selectClass}
          value={filters.kind}
          onChange={(event) => {
            onChange({
              ...filters,
              kind: sourceKinds.find((kind) => kind === event.currentTarget.value) ?? '',
            })
          }}
        >
          <option value="">All types</option>
          {sourceKinds.map((kind) => (
            <option key={kind} value={kind}>
              {sourceLabels[kind]}
            </option>
          ))}
        </select>
      </label>
      <Button
        variant="ghost"
        disabled={!filters.query && !filters.source && !filters.kind}
        onClick={() => {
          onChange({ query: '', source: '', kind: '' })
        }}
      >
        Clear filters
      </Button>
    </form>
  )
}
