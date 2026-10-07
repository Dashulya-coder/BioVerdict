import type { ReactNode } from 'react'

type Tone = 'neutral' | 'fact' | 'assumption' | 'error'
const tones: Record<Tone, string> = {
  neutral: 'border-rule text-muted',
  fact: 'border-accent/25 bg-accent/5 text-accent',
  assumption: 'border-assumption/25 bg-assumption/5 text-assumption',
  error: 'border-danger/25 bg-danger/5 text-danger',
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: Tone }) {
  return (
    <span
      className={`inline-flex items-center rounded-sm border px-2 py-0.5 text-xs leading-5 font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  )
}
