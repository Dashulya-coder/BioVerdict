// How a verdict is coloured wherever it is shown. Colour goes on a mark beside the word (a bar,
// a ring, a square), never on the word itself.
const looks = {
  Invest: { tone: 'positive', fill: 'bg-positive', stroke: 'stroke-positive' },
  Conditional: { tone: 'assumption', fill: 'bg-assumption', stroke: 'stroke-assumption' },
  'Do Not Invest': { tone: 'error', fill: 'bg-danger', stroke: 'stroke-danger' },
} as const
const unknown = { tone: 'neutral', fill: 'bg-muted', stroke: 'stroke-muted' } as const

/** The look of a verdict as the API names it; a name this build does not know stays neutral. */
export function verdictLook(verdict: string | null) {
  return verdict !== null && verdict in looks ? looks[verdict as keyof typeof looks] : unknown
}
