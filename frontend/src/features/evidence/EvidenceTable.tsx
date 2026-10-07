import { formatDate } from '../../app/format'
import { sourceLabels } from '../../app/constants'
import type { Evidence } from '../../app/models'

export function EvidenceTable({
  evidence,
  selectedId,
  onSelect,
}: {
  evidence: readonly Evidence[]
  selectedId: string
  onSelect: (id: string) => void
}) {
  return (
    <div
      role="region"
      aria-label="Evidence list"
      tabIndex={0}
      className="min-w-0 overflow-x-auto border-y border-rule"
    >
      <table className="w-full min-w-[520px] table-fixed text-left text-sm">
        <caption className="sr-only">
          Dated evidence. Select an evidence identifier to read the original quotation.
        </caption>
        <thead className="border-b border-rule text-xs text-muted">
          <tr>
            <th scope="col" className="w-[40%] py-4 pr-4 font-normal">
              Source / evidence
            </th>
            <th scope="col" className="w-[40%] px-4 font-normal">
              Excerpt
            </th>
            <th scope="col" className="w-[20%] pl-4 font-normal">
              Published
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-rule">
          {evidence.map((item) => (
            <tr
              key={item.id}
              className={item.id === selectedId ? 'bg-selected/60' : 'hover:bg-surface'}
            >
              <td
                className={`border-l-2 py-4 pr-3 pl-3 align-top ${item.id === selectedId ? 'border-accent' : 'border-transparent'}`}
              >
                <button
                  type="button"
                  aria-label={`Select ${item.id}`}
                  aria-pressed={item.id === selectedId}
                  onClick={() => {
                    onSelect(item.id)
                  }}
                  className="min-h-11 w-full text-left"
                >
                  <span className="block font-medium">{item.source}</span>
                  <span className="mt-1 block font-mono text-xs text-accent">{item.id}</span>
                  <span className="mt-1 block text-xs text-muted">
                    {sourceLabels[item.source_kind]}
                  </span>
                </button>
              </td>
              <td className="px-4 py-5 align-top">
                <p className="line-clamp-3 text-xs leading-6 text-muted">{item.excerpt}</p>
              </td>
              <td className="py-5 pl-4 align-top font-mono text-[11px] leading-6 text-muted">
                {formatDate(item.published_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
