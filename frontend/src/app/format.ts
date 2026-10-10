const dateFormatter = new Intl.DateTimeFormat('en-GB', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
})
export function formatDate(value: string | null): string {
  return value ? dateFormatter.format(new Date(value.slice(0, 10) + 'T00:00:00Z')) : 'Undated'
}

/** The drug, or for a run without one the mechanism and the indication. */
export function subjectOf(input: { asset: string; mechanism: string; indication: string }): string {
  if (input.asset) return input.asset
  return (
    [input.mechanism, input.indication].filter((part) => part !== '').join(' in ') || 'this run'
  )
}
