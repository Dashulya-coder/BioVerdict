import type { Range } from './schema'

export const percent = (value: number): string => `${(value * 100).toFixed(0)}%`

/** US dollars in millions or billions, signed: "−$8.7M", "$1.2B". */
export function money(value: number): string {
  const sign = value < 0 ? '−' : ''
  const size = Math.abs(value)
  if (size >= 1e9) return `${sign}$${(size / 1e9).toFixed(1)}B`
  if (size >= 1e6) return `${sign}$${(size / 1e6).toFixed(1)}M`
  return `${sign}$${Math.round(size / 1e3).toLocaleString('en-US')}K`
}

export const rangeText = (range: Range, format: (value: number) => string): string =>
  `${format(range.p10)} to ${format(range.p90)}`

export const months = (value: number): string => `${Math.round(value).toString()} mo`
