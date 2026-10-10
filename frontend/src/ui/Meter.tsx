const fills = {
  accent: 'bg-accent',
  positive: 'bg-positive',
  assumption: 'bg-assumption',
  danger: 'bg-danger',
} as const

/** A share of a whole as a bar. Decorative: the number it shows is always written beside it. */
export function Meter({
  value,
  tone = 'accent',
}: {
  /** From 0 to 1; `null` draws an empty track. */
  value: number | null
  tone?: keyof typeof fills
}) {
  const width = value === null ? 0 : Math.min(1, Math.max(0, value)) * 100
  return (
    <span aria-hidden="true" className="block h-1.5 overflow-hidden rounded-full bg-rule">
      <span
        className={`block h-full rounded-full ${fills[tone]}`}
        style={{ width: `${width.toString()}%` }}
      />
    </span>
  )
}
