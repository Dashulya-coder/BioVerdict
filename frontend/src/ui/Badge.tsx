import type { ReactNode } from 'react'

type Tone = 'neutral' | 'fact' | 'assumption' | 'error' | 'positive'
const tones: Record<Tone, string> = {
  neutral: 'border-rule bg-raised text-muted',
  fact: 'border-accent/30 bg-accent/10 text-accent',
  assumption: 'border-assumption/30 bg-assumption/10 text-assumption',
  error: 'border-danger/30 bg-danger/10 text-danger',
  positive: 'border-positive/30 bg-positive/10 text-positive',
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: Tone }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs leading-5 font-medium whitespace-nowrap ${tones[tone]}`}
    >
      {children}
    </span>
  )
}
