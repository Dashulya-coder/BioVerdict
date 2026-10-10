import type { Thesis } from './schema'

/** The parts of the underwriting report the brief names, in its order. */
export const thesisTitles: Record<Thesis['kind'], string> = {
  scientific: 'Scientific thesis',
  translation: 'Human translation thesis',
  development_plan: 'Clinical development plan',
  competitive: 'Competitive landscape',
  commercial: 'Commercial opportunity',
  investment: 'Investment underwriting',
}
