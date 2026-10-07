const dateFormatter = new Intl.DateTimeFormat('en-GB', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
})
export function formatDate(value: string | null): string {
  return value ? dateFormatter.format(new Date(value.slice(0, 10) + 'T00:00:00Z')) : 'Undated'
}
