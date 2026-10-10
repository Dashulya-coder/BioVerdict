import { apiUrl } from './api-client'
import { DEMO_DATE } from './constants'
import type { Origin } from './models'

/** The wording that differs between the prepared snapshot and runs on the API. */
const demo = {
  preparing: 'Preparing the demo input and dated evidence.',
  loadFailed: 'The workspace could not load the demo. Reload this page to try again.',
  intro: 'Start with a drug. Review the resolved input, then explore the evidence behind it.',
  assetHint: 'Available in this demo: Divarasib, GDC-6036 or RG-6330.',
  runBadge: 'Prepared snapshot',
  runNote: 'No live retrieval or model calls.',
  submit: 'Open analysis',
  submitting: 'Opening analysis…',
  reviewStep: 'Check what the fixture resolved and what was inferred.',
  formNote:
    'This demo opens prepared data. It does not perform a new underwriting or reconstruct historical source revisions.',
  resolvedLead:
    'Make the assumptions visible before drawing conclusions. These fields come from the prepared fixture.',
  resolvedBadge: 'Fixture value',
  resolvedNote:
    'Resolver values remain static when you change the evidence cutoff. This review does not verify the assumptions.',
  evidenceLead: 'Prepared evidence',
  noEvidence:
    'This prepared snapshot has no visible evidence for the selected date. Choose another cutoff to explore the fixture.',
  startHint: 'Open the prepared Divarasib demo to review its input and explore the dated evidence.',
}

const api: typeof demo = {
  preparing: 'Contacting the API.',
  loadFailed: 'The workspace could not complete the run. Reload this page to try again.',
  intro:
    'Start with an indication and a mechanism. The API runs it; review the resolved input, then the evidence.',
  assetHint:
    'Optional: name a drug (for example Divarasib or GDC-6036) to analyse it instead of the class.',
  runBadge: 'API run',
  runNote: 'A live API reads public sources and calls a model; a fixture API does neither.',
  submit: 'Run analysis',
  submitting: 'Running analysis…',
  reviewStep: 'Check what the resolver confirmed and what it inferred.',
  formNote:
    'The API decides whether a run is answered from fixtures or live; the workspace shows which. Source revisions older than the cutoff are not reconstructed.',
  resolvedLead:
    'Make the assumptions visible before drawing conclusions. These fields come from the run’s resolver.',
  resolvedBadge: 'Resolved',
  resolvedNote:
    'Identifiers come from database lookups, never from the model. This review does not verify the assumptions.',
  evidenceLead: 'Frozen evidence',
  noEvidence:
    'The bundle of this run has no evidence visible by the selected date. Choose another cutoff and run again.',
  startHint: 'Run an analysis to review its resolved input and explore the dated evidence.',
}

export const apiMode = apiUrl !== ''
export const copy = apiMode ? api : demo

/** The latest cutoff a user may choose: the snapshot date, or today for a run on the API. */
export function latestCutoff(): string {
  if (!apiMode) return DEMO_DATE
  const now = new Date()
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${String(now.getFullYear())}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

export const originLabels: Record<Origin, string> = {
  demo: 'Demo mode',
  fixtures: 'Fixture run',
  live: 'Live run',
}
