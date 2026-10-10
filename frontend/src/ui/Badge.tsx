import type { ReactNode } from 'react'

type Tone = 'neutral' | 'fact' | 'assumption' | 'error' | 'positive'
// The label is always plain text. A status is told by a small square beside it, so that colour
// marks a state and never paints the words.
const markers: Record<Tone, string | null> = {
  neutral: null,
  fact: null,
  assumption: 'bg-assumption',
  error: 'bg-danger',
  positive: 'bg-positive',
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: Tone }) {
  const marker = markers[tone]
  return (
    <span className="inline-flex items-center gap-1.5 rounded-sm border border-rule px-1.5 py-px text-xs leading-5 whitespace-nowrap text-muted">
      {marker ? <span aria-hidden="true" className={`size-1.5 ${marker}`} /> : null}
      {children}
    </span>
  )
}
