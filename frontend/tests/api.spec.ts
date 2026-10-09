import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import type { Page, Route } from '@playwright/test'

// The workspace built with `--mode api`. The tests answer for the BioVerdict API, in the shapes
// of backend `api/schemas.py`, so no backend, source or model is involved.
const API = 'http://127.0.0.1:8000'
const RUN = 'R-20261008-120000-abc123'
const fixtures = join(import.meta.dirname, '..', '..', 'fixtures')

interface FixtureEvidence {
  id: string
  type: string
  [field: string]: unknown
}
const bundle = JSON.parse(readFileSync(join(fixtures, 'bundles', 'divarasib.json'), 'utf8')) as {
  evidence: FixtureEvidence[]
}
const resolver: unknown = JSON.parse(
  readFileSync(join(fixtures, 'resolver', 'divarasib.json'), 'utf8'),
)
const evidence = bundle.evidence.map(({ type, ...item }) => ({
  ...item,
  badge: type,
  claim_ids: [],
}))

interface Event {
  step: string
  status: string
  detail: string
}
const done = (step: string): Event => ({ step, status: 'done', detail: '' })
const started = (step: string): Event => ({ step, status: 'started', detail: '' })
const frozen = [done('resolve'), done('collect'), done('freeze')]

const OTHER = 'R-20261001-090000-def456'
const GROWN = 'R-20261008-121500-fff999'
const side = { verdict: 'Conditional', translation_chain_probability: 0.02 }
const diff = {
  base: {
    ...side,
    run_id: OTHER,
    as_of: '2026-06-30',
    bundle_version: 1,
    evidence_count: 10,
    confidence: 0.77,
  },
  head: {
    ...side,
    run_id: RUN,
    as_of: '2026-10-07',
    bundle_version: 1,
    evidence_count: 11,
    confidence: 0.72,
  },
  verdict_changed: false,
  gates: [{ gate_id: 'S1', kind: 'soft', fired_before: false, fired_after: true }],
  chain: [{ link: 'patient_benefit', status_before: 'missing', status_after: 'weak' }],
  evidence_added: [{ ...evidence[4], claim_ids: ['C-0017'] }],
  evidence_removed: [],
  claims: [
    {
      change: 'added',
      section: 'translation',
      text: 'Divarasib improved progression-free survival over the approved inhibitors',
      before: null,
      after: {
        id: 'C-0017',
        basis: 'extracted',
        confidence: 0.65,
        gate_signals: [],
        critical: true,
      },
      new_evidence_ids: ['E-0005'],
    },
  ],
  unchanged_claims: 8,
  matching: 'Claims are paired by section and identical wording.',
}
const summary = (run_id: string, as_of: string) => ({
  run_id,
  status: 'done',
  verdict: 'Conditional',
  as_of,
  created_at: '2026-10-08T12:00:00Z',
  finished_at: '2026-10-08T12:00:05Z',
  input: { asset: 'divarasib' },
})

interface Api {
  /** How the API answers a request to add evidence; default: it starts run GROWN. */
  grow?: { status: number; body: unknown }
  asked?: string[]
  mode?: 'fixtures' | 'live'
  /** What the trace shows on each successive poll; the last entry repeats. */
  traces?: Event[][]
  start?: { status: number; body: unknown }
  posted?: unknown[]
}

async function serve(page: Page, api: Api = {}) {
  const traces = [...(api.traces ?? [frozen])]
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({
      status,
      contentType: 'application/json',
      headers: { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*' },
      body: JSON.stringify(body),
    })
  await page.route('**/*', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (url.hostname !== '127.0.0.1') throw new Error(`Unexpected external request: ${url.href}`)
    if (url.origin !== API) return route.continue()
    if (request.method() === 'OPTIONS') return json(route, {})
    if (url.pathname === '/health') return json(route, { status: 'ok', mode: api.mode ?? 'live' })
    if (url.pathname === '/runs' && request.method() === 'POST') {
      api.posted?.push(request.postDataJSON())
      return api.start
        ? json(route, api.start.body, api.start.status)
        : json(route, { run_id: RUN, status: 'running' }, 202)
    }
    if (url.pathname === `/runs/${RUN}/trace`) {
      const events = traces.length > 1 ? traces.shift() : traces[0]
      return json(route, { run_id: RUN, events, llm_calls: [], totals: {} })
    }
    if (url.pathname === '/runs' && request.method() === 'GET')
      return json(route, [summary(RUN, '2026-10-07'), summary(OTHER, '2026-06-30')])
    if (url.pathname.endsWith('/diff')) {
      api.asked?.push(url.pathname + url.search)
      return json(route, diff)
    }
    if (url.pathname === `/runs/${RUN}/evidence` && request.method() === 'POST') {
      api.posted?.push(request.postDataJSON())
      return api.grow
        ? json(route, api.grow.body, api.grow.status)
        : json(route, { run_id: GROWN, status: 'running' }, 202)
    }
    if (url.pathname === `/runs/${GROWN}`) return json(route, summary(GROWN, '2026-10-08'))
    if (url.pathname === `/runs/${RUN}/resolver`) return json(route, resolver)
    if (url.pathname === `/runs/${RUN}/evidence`) return json(route, evidence)
    return json(route, { detail: `no such route: ${url.pathname}` }, 404)
  })
}

async function run(page: Page, asset: string) {
  await page.goto('/')
  await page.getByLabel('Asset / drug').fill(asset)
  await page.getByRole('button', { name: 'Run analysis' }).click()
}

test('a run on the API shows its progress, its resolved input and its whole bundle', async ({
  page,
}) => {
  const posted: unknown[] = []
  await serve(page, {
    posted,
    traces: [[started('resolve')], [done('resolve'), started('collect')], frozen],
  })
  await page.goto('/')
  await expect(page.getByText('API', { exact: true })).toBeVisible()
  await page.getByLabel('Asset / drug').fill(' GDC-6036 ')
  await page.getByLabel('Evidence cutoff').fill('2026-10-01')
  await page.getByRole('button', { name: 'Run analysis' }).click()
  await expect(page.getByRole('status')).toContainText(/Resolving|Collecting/)

  await expect(
    page.getByRole('heading', { name: 'Review the resolved input', exact: true }),
  ).toBeVisible()
  expect(posted).toEqual([{ asset: 'GDC-6036', as_of: '2026-10-01' }])
  await expect(page.getByText('Live run', { exact: true })).toBeVisible()
  await expect(page.getByText(RUN, { exact: true })).toBeVisible()
  await expect(page.getByText('non-small cell lung carcinoma')).toBeVisible()
  await expect(page.getByText('Assumption', { exact: true }).first()).toBeVisible()

  await page.getByRole('button', { name: 'Explore evidence' }).click()
  await expect(page.getByRole('status').first()).toContainText('15 of 15 evidence items')
  const detail = page.getByRole('complementary', { name: 'Evidence detail' })
  await expect(detail.getByRole('heading', { name: 'E-0001' })).toBeVisible()
  await expect(detail.getByText('Source fact', { exact: true })).toBeVisible()
})

test('a fixture API is labelled as such, never as a live run', async ({ page }) => {
  await serve(page, { mode: 'fixtures' })
  await run(page, 'divarasib')
  await expect(page.getByText('Fixture run', { exact: true })).toBeVisible()
  await expect(page.getByText('Live run', { exact: true })).toHaveCount(0)
})

test('a refusal is shown in the words of the API, and editing clears it', async ({ page }) => {
  const posted: unknown[] = []
  await serve(page, {
    posted,
    start: { status: 422, body: { detail: 'fixture mode knows only these assets: divarasib' } },
  })
  await run(page, 'Unknown drug')
  await expect(page.getByRole('alert')).toContainText('knows only these assets: divarasib')
  await expect(page.getByRole('button', { name: 'Reload workspace' })).toHaveCount(0)
  await page.getByLabel('Asset / drug').fill('divarasib')
  await expect(page.getByRole('alert')).toHaveCount(0)
  expect(posted).toHaveLength(1)
})

test('a failed run gives its reason instead of an empty analysis', async ({ page }) => {
  const reason = "ResolverError: no target could be identified from: 'zzz'"
  await serve(page, {
    traces: [[started('resolve')], [{ step: 'run', status: 'failed', detail: reason }]],
  })
  await run(page, 'zzz')
  await expect(page.getByRole('alert')).toContainText(`The run failed: ${reason}`)
  await expect(page.getByRole('heading', { name: 'New analysis', exact: true })).toBeVisible()
})

test('an API that does not answer is named, with what to do', async ({ page }) => {
  await page.route(`${API}/**`, (route) => route.abort('connectionrefused'))
  await run(page, 'divarasib')
  await expect(page.getByRole('alert')).toContainText(`${API} did not answer`)
  await expect(page.getByRole('alert')).toContainText('Start the backend')
})

test('an answer in an unknown shape is rejected, not shown', async ({ page }) => {
  await serve(page, { start: { status: 202, body: { id: 7 } } })
  await run(page, 'divarasib')
  await expect(page.getByRole('alert')).toContainText('a shape this workspace does not understand')
})

test('two runs are compared: verdict, gates, new evidence and the claims resting on it', async ({
  page,
}) => {
  const asked: string[] = []
  await serve(page, { asked })
  await run(page, 'divarasib')
  await page.getByRole('link', { name: 'Compare', exact: true }).click()
  await page.getByRole('combobox', { name: 'Earlier run' }).selectOption(OTHER)
  await page.getByRole('button', { name: 'Compare', exact: true }).click()

  await expect(page.getByText('The verdict stayed Conditional.')).toBeVisible()
  expect(asked).toEqual([`/runs/${RUN}/diff?against=${OTHER}`])
  await expect(page.getByText('Gate S1: not fired → fired')).toBeVisible()
  await expect(page.getByText('Chain link patient benefit: missing → weak')).toBeVisible()
  const added = page.getByRole('region', { name: 'Evidence only in the later run' })
  await expect(added.getByText('E-0005', { exact: true })).toBeVisible()
  await expect(added.getByText('quoted by C-0017')).toBeVisible()
  const claims = page.getByRole('region', { name: 'Claims' })
  await expect(claims.getByText('New claim', { exact: true })).toBeVisible()
  await expect(
    claims.getByText('Rests on evidence the earlier run did not have: E-0005'),
  ).toBeVisible()
  await expect(page.getByText('not by a model')).toBeVisible()
})

async function fillDocument(page: Page) {
  await page.getByRole('link', { name: 'Compare', exact: true }).click()
  await page
    .getByLabel('Verbatim excerpt')
    .fill('The study met its primary endpoint of progression-free survival.')
  await page.getByLabel('Source address').fill('https://www.example.org/news/1')
  await page.getByLabel('Source name').fill('Example release')
  await page.getByLabel('Published').fill('2026-09-01')
  await page.getByRole('combobox', { name: 'Added source type' }).selectOption('company')
  await page.getByRole('button', { name: 'Add and recompute' }).click()
}

test('an added document starts a recompute and shows what it changed', async ({ page }) => {
  const posted: unknown[] = []
  const asked: string[] = []
  await serve(page, { posted, asked })
  await run(page, 'divarasib')
  await fillDocument(page)

  await expect(page.getByText('The verdict stayed Conditional.')).toBeVisible()
  expect(posted.at(-1)).toMatchObject({
    evidence: [
      {
        text: 'The study met its primary endpoint of progression-free survival.',
        url: 'https://www.example.org/news/1',
        source: 'Example release',
        source_kind: 'company',
        level: 'human_interventional',
        published_at: '2026-09-01',
      },
    ],
  })
  expect(asked).toEqual([`/runs/${GROWN}/diff`])
})

test('a fixture API that cannot reason over new evidence says so', async ({ page }) => {
  await serve(page, {
    mode: 'fixtures',
    grow: { status: 422, body: { detail: 'fixture runs cannot reason over new evidence' } },
  })
  await run(page, 'divarasib')
  await fillDocument(page)
  await expect(page.getByRole('alert')).toContainText(
    'fixture runs cannot reason over new evidence',
  )
})
