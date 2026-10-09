import { Badge } from '../../ui/Badge'
import { rangeText } from './numbers'
import type { Range } from './schema'

/** One modeled quantity: the middle value, the P10–P90 range, and a note when it is missing. */
export function RangeStat({
  label,
  range,
  format,
  missing,
}: {
  label: string
  range: Range | null
  format: (value: number) => string
  missing: string
}) {
  return (
    <div className="border-l border-rule pl-4">
      <dt className="text-xs text-muted">{label}</dt>
      {range ? (
        <dd>
          <span className="font-editorial text-2xl">{format(range.p50)}</span>
          <span className="mt-1 block text-xs text-muted">
            P10 to P90: {rangeText(range, format)}
          </span>
          <span className="mt-2 block">
            <Badge tone="assumption">Modeled</Badge>
          </span>
        </dd>
      ) : (
        <dd className="mt-1 text-sm text-muted">{missing}</dd>
      )}
    </div>
  )
}
