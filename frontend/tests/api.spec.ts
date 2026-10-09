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

interface Api {
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
