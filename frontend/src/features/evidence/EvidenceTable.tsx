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
      <table className="w-full min-w-[480px] table-fixed text-left text-sm">
        <caption className="sr-only">
          Dated evidence. Select an evidence identifier to read the original quotation.
        </caption>
        <thead className="border-b border-rule text-xs text-muted">
          <tr>
            <th scope="col" className="w-[18%] py-4 pr-3 pl-3 font-normal">
              ID
            </th>
            <th scope="col" className="w-[25%] px-3 font-normal">
              Published
            </th>
            <th scope="col" className="w-[35%] px-3 font-normal">
              Source
            </th>
            <th scope="col" className="w-[22%] pr-3 pl-3 font-normal">
              Type
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-rule">
          {evidence.map((item) => (
            <tr
              key={item.id}
              className={item.id === selectedId ? 'bg-selected' : 'hover:bg-surface'}
            >
              <td
                className={`border-l-2 pr-3 pl-3 ${item.id === selectedId ? 'border-accent' : 'border-transparent'}`}
              >
                <button
                  type="button"
                  aria-label={`Select ${item.id}`}
                  aria-pressed={item.id === selectedId}
                  onClick={() => {
                    onSelect(item.id)
                  }}
                  className="min-h-11 w-full py-3 text-left font-mono text-xs text-ink"
                >
                  {item.id}
                </button>
              </td>
              <td className="px-3 py-4 font-mono text-[11px] leading-6 text-muted">
                {formatDate(item.published_at)}
              </td>
              <td className="px-3 py-4 text-xs leading-6 break-words">{item.source}</td>
              <td className="px-3 py-4 text-xs leading-6 text-muted">
                {sourceLabels[item.source_kind]}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
