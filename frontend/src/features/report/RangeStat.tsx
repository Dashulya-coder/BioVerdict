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
    <div className="bg-surface p-5">
      <dt className="text-xs text-muted">{label}</dt>
      {range ? (
        <dd className="mt-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="figure text-2xl">{format(range.p50)}</span>
            <Badge tone="assumption">Modeled</Badge>
          </span>
          <span className="mt-1 block text-xs text-muted">
            P10 to P90: {rangeText(range, format)}
          </span>
        </dd>
      ) : (
        <dd className="mt-2 text-xs leading-5 text-muted">{missing}</dd>
      )}
    </div>
  )
}
