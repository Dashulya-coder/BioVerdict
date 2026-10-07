import { sourceLabels } from '../../app/constants'
import { Badge } from '../../ui/Badge'
import { Button } from '../../ui/Button'
import type { SourceGroup } from './filters'

export function SourceList({
  groups,
  selectedId,
  onSelect,
}: {
  groups: readonly SourceGroup[]
  selectedId: string
  onSelect: (id: string) => void
}) {
  return (
    <ul aria-label="Source list" className="min-w-0 divide-y divide-rule border-y border-rule">
      {groups.map((group) => (
        <li key={group.first.url} className="py-5">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-sm font-medium">{group.first.source}</h2>
            <Badge>{sourceLabels[group.first.source_kind]}</Badge>
          </div>
          <p className="font-mono text-[10px] leading-6 break-all text-muted">{group.first.url}</p>
          <p className="mt-3 text-xs text-muted">
            {group.items.length} evidence {group.items.length === 1 ? 'item' : 'items'} from this
            source
          </p>
          <div className="mt-2 flex flex-wrap gap-1">
            {group.items.map((item) => (
              <Button
                key={item.id}
                variant={item.id === selectedId ? 'secondary' : 'ghost'}
                className="px-2 font-mono text-xs"
                aria-label={`Select ${item.id}`}
                aria-pressed={item.id === selectedId}
                onClick={() => {
                  onSelect(item.id)
                }}
              >
                {item.id}
              </Button>
            ))}
          </div>
        </li>
      ))}
    </ul>
  )
}
