// The six underwriting modules and their answers (backend `scoring/module_answers.py`).
export const moduleAnswers = ['supports', 'mixed', 'against', 'insufficient'] as const
export type ModuleAnswer = (typeof moduleAnswers)[number]

export const answerLabels: Record<ModuleAnswer, string> = {
  supports: 'Supports the case',
  mixed: 'Mixed',
  against: 'Weighs against',
  insufficient: 'Not enough evidence',
}
export const answerTones = {
  supports: 'positive',
  mixed: 'assumption',
  against: 'error',
  insufficient: 'neutral',
} as const

/** A balance or a pull with its sign: "+0.62", "−0.40"; "n/a" when nothing carries weight. */
export function signed(value: number | null): string {
  if (value === null) return 'n/a'
  const text = Math.abs(value).toFixed(2)
  return value < 0 ? `−${text}` : `+${text}`
}
