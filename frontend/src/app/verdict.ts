// How a verdict is coloured wherever it is shown. The word is always written beside the colour.
const looks = {
  Invest: { tone: 'positive', text: 'text-positive', fill: 'bg-positive' },
  Conditional: { tone: 'assumption', text: 'text-assumption', fill: 'bg-assumption' },
  'Do Not Invest': { tone: 'error', text: 'text-danger', fill: 'bg-danger' },
} as const
const unknown = { tone: 'neutral', text: 'text-ink', fill: 'bg-muted' } as const

/** The look of a verdict as the API names it; a name this build does not know stays neutral. */
export function verdictLook(verdict: string | null) {
  return verdict !== null && verdict in looks ? looks[verdict as keyof typeof looks] : unknown
}
