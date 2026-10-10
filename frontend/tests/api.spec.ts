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
const report = JSON.parse(readFileSync(join(import.meta.dirname, 'report.json'), 'utf8')) as {
  executive: Record<string, unknown>
}
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
  modules: [
    {
      module: 'clinical_development',
      title: 'Clinical development',
      answer_before: 'supports',
      answer_after: 'mixed',
      balance_before: 0.61,
      balance_after: 0.12,
      headline_before: 'The evidence supports the case',
      headline_after:
        'The evidence points both ways: favourable weight 0.90 against unfavourable 0.71',
      changed: true,
      causes: [
        {
          evidence_id: 'E-0016',
          source: 'Example congress abstract',
          url: 'https://www.example.org/abstract/1',
          published_at: '2026-09-01',
          level: 'human_interventional',
          direction: 'contradicts',
          quote: 'no confirmed responses were observed in the expansion cohort',
          claim_id: 'C-0007',
          claim_text: 'Divarasib gave a confirmed response in 53.4% of patients',
          claim_change: 'changed',
          confidence_before: 0.77,
          confidence_after: 0.5,
          contribution_before: 0.54,
          contribution_after: 0,
        },
      ],
    },
    {
      module: 'mechanism_validation',
      title: 'Mechanism and biological validation',
      answer_before: 'supports',
      answer_after: 'supports',
      balance_before: 1,
      balance_after: 1,
      headline_before: 'The evidence supports the case',
      headline_after: 'The evidence supports the case',
      changed: false,
      causes: [],
    },
  ],
  gates: [{ gate_id: 'S1', kind: 'soft', fired_before: false, fired_after: true }],
  chain: [
    {
      link: 'patient_benefit',
      status_before: 'missing',
      status_after: 'weak',
      confidence_before: null,
      confidence_after: 0.45,
    },
  ],
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
  input?: Record<string, unknown>
  resolver?: unknown
  evidence?: unknown
  /** How the API answers a request to add evidence; default: it starts run GROWN. */
  grow?: { status: number; body: unknown }
  asked?: string[]
  mode?: 'fixtures' | 'live'
  /** What the trace shows on each successive poll; the last entry repeats. */
  traces?: Event[][]
  start?: { status: number; body: unknown }
  posted?: unknown[]
  /** The status of run RUN on each successive poll; the last entry repeats. Default: done. */
  statuses?: string[]
  /** Paths the API accepts and never answers. */
  silent?: string[]
  /** The model calls the trace of RUN lists. */
  calls?: unknown[]
  /** The tornado bars the financials of RUN list. */
  tornado?: unknown[]
  /** The report the API serves for RUN; default: the fixture run's. */
  report?: unknown
}

async function serve(page: Page, api: Api = {}) {
  const traces = [...(api.traces ?? [frozen])]
  const statuses = [...(api.statuses ?? ['done'])]
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
    if (api.silent?.includes(url.pathname)) return // accepted, never answered
    if (url.pathname === '/health') return json(route, { status: 'ok', mode: api.mode ?? 'live' })
    if (url.pathname === `/runs/${RUN}`) {
      const status = statuses.length > 1 ? statuses.shift() : statuses[0]
      const verdict = status === 'done' ? 'Conditional' : null
      return json(route, {
        ...summary(RUN, '2026-10-07'),
        status,
        verdict,
        input: api.input ?? { asset: 'divarasib' },
      })
    }
    if (url.pathname === '/runs' && request.method() === 'POST') {
      api.posted?.push(request.postDataJSON())
      return api.start
        ? json(route, api.start.body, api.start.status)
        : json(route, { run_id: RUN, status: 'running' }, 202)
    }
    if (url.pathname === `/runs/${RUN}/trace`) {
      const events = traces.length > 1 ? traces.shift() : traces[0]
      const llm_calls = api.calls ?? []
      const cost_usd = llm_calls.reduce<number>(
        (sum, call) => sum + (call as { cost_usd: number }).cost_usd,
        0,
      )
      const totals = { input_tokens: 0, output_tokens: 0, cost_usd, calls: llm_calls.length }
      return json(route, {
        run_id: RUN,
        events: events?.map((event, seq) => ({ seq, ...event })),
        llm_calls,
        totals,
      })
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
    if (url.pathname === `/runs/${RUN}`) return json(route, summary(RUN, '2026-10-07'))
    if (url.pathname === `/runs/${RUN}/financials`)
      return json(route, {
        tornado: api.tornado ?? [],
        missing: ['the market could not be sized.'],
      })
    if (url.pathname === `/runs/${RUN}/report`) return json(route, api.report ?? report)
    if (url.pathname === `/runs/${GROWN}`) return json(route, summary(GROWN, '2026-10-08'))
    if (url.pathname === `/runs/${RUN}/resolver`) return json(route, api.resolver ?? resolver)
    if (url.pathname === `/runs/${RUN}/evidence`) return json(route, api.evidence ?? evidence)
    return json(route, { detail: `no such route: ${url.pathname}` }, 404)
  })
}

async function run(page: Page, asset: string) {
  await page.goto('/')
  await page.getByLabel('Asset / drug').fill(asset)
  await page.getByRole('button', { name: 'Run analysis' }).click()
}

/** Runs and waits until the analysis is ready, so that a later navigation is not overridden. */
async function openRun(page: Page, asset: string) {
  await run(page, asset)
  await expect(
    page.getByRole('heading', { name: 'Review the resolved input', exact: true }),
  ).toBeVisible()
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

test('an indication with a mechanism is enough to start a run, and empty fields are not sent', async ({
  page,
}) => {
  const posted: unknown[] = []
  await serve(page, { posted })
  await page.goto('/')
  await page.getByLabel('Asset / drug').fill('')
  await page.getByLabel('Indication (optional)').fill('non-small cell lung cancer')
  await page.getByLabel('Mechanism / target (optional)').fill('KRAS G12C inhibitor')
  await page.getByLabel('Evidence cutoff').fill('2026-10-01')
  await page.getByRole('button', { name: 'Run analysis' }).click()
  await expect(
    page.getByRole('heading', { name: 'Review the resolved input', exact: true }),
  ).toBeVisible()
  expect(posted).toEqual([
    {
      indication: 'non-small cell lung cancer',
      mechanism: 'KRAS G12C inhibitor',
      as_of: '2026-10-01',
    },
  ])
})

test('a form with neither a drug nor an indication and mechanism is refused', async ({ page }) => {
  await serve(page)
  await page.goto('/')
  await page.getByLabel('Asset / drug').fill('')
  await page.getByLabel('Indication (optional)').fill('lung cancer')
  await page.getByRole('button', { name: 'Run analysis' }).click()
  await expect(page.getByRole('alert')).toContainText('indication together with a mechanism')
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
  await openRun(page, 'divarasib')
  await page.getByRole('link', { name: 'Compare', exact: true }).click()
  await page.getByRole('combobox', { name: 'Earlier run' }).selectOption(OTHER)
  await page.getByRole('button', { name: 'Compare', exact: true }).click()

  await expect(page.getByText('The verdict stayed Conditional.')).toBeVisible()
  expect(asked).toEqual([`/runs/${RUN}/diff?against=${OTHER}`])
  await expect(page.getByText('Gate S1: not fired → fired')).toBeVisible()
  await expect(
    page.getByText('Chain link patient benefit: missing → weak, confidence Not computed → 0.45'),
  ).toBeVisible()
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
  await openRun(page, 'divarasib')
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
  await openRun(page, 'divarasib')
  await fillDocument(page)
  await expect(page.getByRole('alert')).toContainText(
    'fixture runs cannot reason over new evidence',
  )
})

test('the header says whether the run is still reasoning, and Compare waits for it', async ({
  page,
}) => {
  await serve(page, { statuses: ['running', 'running', 'running', 'done'] })
  await run(page, 'divarasib')
  await expect(page.getByText('Reasoning…', { exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'Compare', exact: true }).click()
  await expect(page.getByText('This run is still reasoning over its evidence.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Add and recompute' })).toBeDisabled()

  await expect(page.getByText('Verdict: Conditional', { exact: true })).toBeVisible()
  await expect(page.getByText('This run is still reasoning over its evidence.')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Add and recompute' })).toBeEnabled()
})

test('the comparison of a class run names the mechanism and the indication', async ({ page }) => {
  await serve(page, { input: { indication: 'multiple sclerosis', mechanism: 'BTK inhibitor' } })
  await page.goto(`/?run=${RUN}#compare`)
  await expect(
    page.getByText('See what moved the report of BTK inhibitor in multiple sclerosis:'),
  ).toBeVisible()
})

test('a failed run is named in the header and cannot be compared', async ({ page }) => {
  await serve(page, { statuses: ['failed'] })
  await run(page, 'divarasib')
  await expect(page.getByText('Run failed', { exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'Compare', exact: true }).click()
  await expect(page.getByText('This run failed, so it has no report to compare.')).toBeVisible()
})

test('a reload reopens the run on the same screen without starting another', async ({ page }) => {
  const posted: unknown[] = []
  await serve(page, { posted })
  await run(page, 'divarasib')
  await page.getByRole('button', { name: 'Explore evidence' }).click()
  await expect(page).toHaveURL(new RegExp(`\\?run=${RUN}#evidence$`))

  await page.reload()

  await expect(page.getByRole('status').first()).toContainText('15 of 15 evidence items')
  await expect(page.getByText(RUN, { exact: true })).toBeVisible()
  await expect(page.getByText('Verdict: Conditional', { exact: true })).toBeVisible()
  expect(posted).toHaveLength(1) // the run was read again, not started again
})

test('a link to a run that does not exist says so and offers a new analysis', async ({ page }) => {
  await serve(page)
  await page.goto('/?run=R-unknown#evidence')
  await expect(page.getByRole('alert')).toContainText('no such route')
  await page.getByRole('button', { name: 'New analysis' }).click()
  await expect(page.getByLabel('Asset / drug')).toBeVisible()
})

test('a request that is accepted and never answered ends with a message', async ({ page }) => {
  await page.clock.install()
  await serve(page, { silent: ['/health'] })
  await run(page, 'divarasib')
  await expect(page.getByRole('status')).toContainText('Contacting the API')

  await page.clock.fastForward(21_000)

  await expect(page.getByRole('alert')).toContainText('did not answer within 20 seconds')
})

test('the report opens with the verdict, the modeled figures and what is missing', async ({
  page,
}) => {
  await serve(page)
  await openRun(page, 'divarasib')
  await page.getByRole('link', { name: 'Report' }).click()
  const summary = page.getByRole('region', { name: 'Executive verdict' })
  await expect(summary.getByText('Conditional', { exact: true })).toBeVisible()
  await expect(summary.getByText('Top risks')).toBeVisible()
  await expect(summary.getByText('What would change our mind')).toBeVisible()
  await expect(summary.getByText('Not computed: the market could not be sized.')).toBeVisible()
})

test('the translation chain names every link and draws a missing one as missing', async ({
  page,
}) => {
  await serve(page)
  await openRun(page, 'divarasib')
  await page.getByRole('link', { name: 'Report' }).click()
  const chain = page.getByRole('region', { name: 'Translation chain' })
  await expect(chain.getByRole('listitem')).toHaveCount(5)
  await expect(chain.getByText('Human exposure')).toBeVisible()
  await expect(chain.getByText('Missing', { exact: true }).first()).toBeVisible()
  await expect(chain.getByText('Supported', { exact: true }).first()).toBeVisible()
})

test('a claim opens onto its verbatim quotation and the original source', async ({ page }) => {
  await serve(page)
  await openRun(page, 'divarasib')
  await page.getByRole('link', { name: 'Report' }).click()
  const claim = page.getByText('KRAS G12C is a frequent, poor-prognosis driver mutation in NSCLC')
  await expect(claim).toBeVisible()
  await expect(page.getByText('found in approximately 14% of NSCLC cases')).toBeHidden()
  await claim.click()
  await expect(
    page.getByText(
      '“found in approximately 14% of NSCLC cases and associated with poor prognosis”',
    ),
  ).toBeVisible()
  await expect(
    page.getByRole('link', { name: 'Open the original source: Roche press release' }).first(),
  ).toHaveAttribute('href', 'https://www.roche.com/media/releases/med-cor-2026-07-02')
  await expect(
    page.getByText('Not searched: this proves nothing either way.').first(),
  ).toBeVisible()
})

test('a claim whose quotation the judge removed says so and why', async ({ page }) => {
  const judged = structuredClone(report) as unknown as {
    sections: { section: string; status: string; claims: Record<string, unknown>[] }[]
  }
  const mechanism = judged.sections.find((s) => s.section === 'mechanism')
  const claim = mechanism?.claims[0]
  if (!claim) throw new Error('the fixture report has no mechanism claim')
  claim.links = []
  claim.checks = [
    {
      check: 'entailment',
      detail: 'E-0001 cited as supports, judged unrelated: the quote gives only the unit',
    },
  ]
  const translation = judged.sections.find((s) => s.section === 'translation')
  if (translation) translation.status = 'not_searched'
  await serve(page, { report: judged })
  await openRun(page, 'divarasib')
  await page.getByRole('link', { name: 'Report' }).click()

  await page.getByText(String(claim.text)).click()
  const opened = page.locator('details', { hasText: String(claim.text) })
  await expect(opened.getByText('No quotation is left to support this claim.')).toBeVisible()
  await expect(opened.getByText('The judge removed a quotation')).toBeVisible()
  await expect(opened.getByText('judged unrelated: the quote gives only the unit')).toBeVisible()
  await expect(opened.getByText('it is a stated gap')).toBeHidden()
  // Translation reads the other sections: it is not a section that was never searched.
  await expect(page.getByText('read from the other sections')).toBeVisible()
})

test('a quotation the judge did not read is not shown as checked', async ({ page }) => {
  const mixed = structuredClone(report) as unknown as {
    sections: { section: string; claims: { text: string; links: { judged?: string }[] }[] }[]
  }
  const claims = mixed.sections.flatMap((s) => s.claims).filter((c) => c.links.length > 0)
  const [read, context, silent] = claims
  if (!read || !context || !silent) throw new Error('the fixture report needs three cited claims')
  for (const link of read.links) link.judged = 'judged'
  for (const link of context.links) link.judged = 'not_judged'
  for (const link of silent.links) link.judged = 'no_answer'
  await serve(page, { report: mixed })
  await openRun(page, 'divarasib')
  await page.getByRole('link', { name: 'Report' }).click()

  const row = (text: string) => page.locator('details', { hasText: text })
  await expect(row(read.text).getByText('Quotes not judged')).toBeHidden()
  await expect(row(context.text).getByText('Quotes not judged')).toBeVisible()
  await expect(row(silent.text).getByText('Quotes not judged')).toBeVisible()

  await page.getByText(context.text).click()
  await expect(row(context.text).getByText('Not read by the judge').first()).toBeVisible()
  await page.getByText(silent.text).click()
  await expect(row(silent.text).getByText('The judge gave no answer').first()).toBeVisible()
  await page.getByText(read.text).click()
  await expect(row(read.text).getByText('Not read by the judge')).toBeHidden()
})

test('a top risk leads to its claim and then to the quotation', async ({ page }) => {
  const risky = structuredClone(report) as unknown as {
    executive: Record<string, unknown>
    sections: { section: string; claims: { id: string; text: string }[] }[]
  }
  const claim = risky.sections.find((s) => s.section === 'mechanism')?.claims[0]
  if (!claim) throw new Error('the fixture report has no mechanism claim')
  risky.executive.top_risks = [claim.text]
  risky.executive.top_risk_claims = [[claim.id]]
  await serve(page, { report: risky })
  await openRun(page, 'divarasib')
  await page.getByRole('link', { name: 'Report' }).click()

  await page.getByRole('button', { name: claim.id }).click()
  const opened = page.locator('details', { hasText: claim.text }).last()
  await expect(opened).toHaveAttribute('open', '')
  await expect(opened.getByText('Open the original source').first()).toBeVisible()
})

test('what is unknown is listed by the diligence that could answer it', async ({ page }) => {
  await serve(page)
  await openRun(page, 'divarasib')
  await page.getByRole('link', { name: 'Report' }).click()
  const unknown = page.getByRole('region', { name: 'What we do not know' })
  await expect(unknown.getByText('Patient-level data', { exact: true })).toBeVisible()
  await expect(unknown.getByText('Expert interview', { exact: true })).toBeVisible()
  await expect(unknown.getByText('Target engagement in tumour tissue is not shown')).toBeVisible()
})

test('modeled ranges are labelled and shown as P10 to P90', async ({ page }) => {
  const range = (p10: number, p50: number, p90: number) => ({ p10, p50, p90 })
  const modeled = {
    ...report,
    executive: {
      ...report.executive,
      pos: range(0.2, 0.4, 0.6),
      rnpv: range(-18_000_000, -8_700_000, 6_300_000),
      capital: range(98_000_000, 136_000_000, 191_000_000),
      capital_to_milestone: range(9_000_000, 20_000_000, 38_000_000),
      months_to_milestone: range(15, 20, 25),
    },
  }
  await serve(page, { report: modeled })
  await openRun(page, 'divarasib')
  await page.getByRole('link', { name: 'Report' }).click()
  const summary = page.getByRole('region', { name: 'Executive verdict' })
  await expect(summary.getByText('−$8.7M')).toBeVisible()
  await expect(summary.getByText('P10 to P90: −$18.0M to $6.3M')).toBeVisible()
  await expect(summary.getByText('Modeled').first()).toBeVisible()
  await expect(summary.getByText('Capital to next milestone')).toBeVisible()
  await expect(summary.getByText('$20.0M')).toBeVisible()
})

test('a report that is not ready or failed says so', async ({ page }) => {
  await serve(page, { report: { detail: 'unexpected' } })
  await openRun(page, 'divarasib')
  await page.getByRole('link', { name: 'Report' }).click()
  await expect(page.getByRole('alert')).toContainText('shape this workspace does not understand')
})

const call = {
  step: 'reason.mechanism',
  provider: 'openai',
  model: 'gpt-x',
  input_tokens: 1200,
  output_tokens: 300,
  cost_usd: 0.05,
  latency_ms: 83000,
  attempts: 2,
  cache_hit: false,
  failover_from: null,
  error: null,
}

test('the trace screen shows the cost, the cost by step and every call', async ({ page }) => {
  await serve(page, {
    calls: [call, { ...call, step: 'reason.clinical', cost_usd: 0.1, failover_from: 'claude-y' }],
  })
  await openRun(page, 'divarasib')
  await page.getByRole('link', { name: 'Trace' }).click()
  const cost = page.getByRole('region', { name: 'Cost of the run' })
  await expect(cost.getByText('$0.15')).toBeVisible()
  await expect(cost.getByText('Mixed models: 1 calls failed over')).toBeVisible()
  const steps = page.getByRole('region', { name: 'Cost by step' })
  await expect(steps.getByRole('row')).toHaveCount(3)
  const calls = page.getByRole('region', { name: 'Every model call' })
  await expect(calls.getByText('2 attempts')).toHaveCount(2)
  await expect(calls.getByText('from claude-y')).toBeVisible()
  await expect(page.getByRole('region', { name: 'Steps in order' })).toBeVisible()
})

test('the trace screen of a run with no model call says so', async ({ page }) => {
  await serve(page)
  await openRun(page, 'divarasib')
  await page.getByRole('link', { name: 'Trace' }).click()
  await expect(page.getByText('This run has made no model call yet.')).toBeVisible()
})

test('the gates list shows which gate fired and the claims behind it', async ({ page }) => {
  await serve(page)
  await openRun(page, 'divarasib')
  await page.getByRole('link', { name: 'Report' }).click()
  const gates = page.getByRole('region', { name: 'Gates' })
  await expect(gates.getByRole('listitem')).toHaveCount(11)
  await expect(gates.getByText('Fired', { exact: true })).toHaveCount(1)
  await expect(gates.getByText('Claims: C-0014, C-0015')).toBeVisible()
})

test('the tornado shows each input with the rNPV at its low and high end', async ({ page }) => {
  await serve(page, {
    tornado: [
      { input: 'peak_share', at_low: -20e6, at_high: 180e6 },
      { input: 'discount_rate', at_low: 10e6, at_high: 30e6 },
    ],
  })
  await openRun(page, 'divarasib')
  await page.getByRole('link', { name: 'Report' }).click()
  const bars = page.getByRole('region', { name: 'What moves the rNPV' })
  await expect(bars.getByText('peak share')).toBeVisible()
  await expect(bars.getByText('−$20.0M')).toBeVisible()
  await expect(bars.getByText('$180.0M')).toBeVisible()
})

test('the tornado says why it is empty', async ({ page }) => {
  await serve(page)
  await openRun(page, 'divarasib')
  await page.getByRole('link', { name: 'Report' }).click()
  await expect(page.getByText('Not computed: the market could not be sized.')).toHaveCount(2)
})

test('diligence questions are ranked by the value of their answer', async ({ page }) => {
  const ranked = {
    ...report,
    diligence_questions: [
      {
        text: 'Is exposure reached in tumor?',
        answered_by: 'experiment',
        value_of_information: 0.2,
      },
      {
        text: 'Why did the sponsor pause?',
        answered_by: 'kol_interview',
        value_of_information: 0.7,
      },
    ],
  }
  await serve(page, { report: ranked })
  await openRun(page, 'divarasib')
  await page.getByRole('link', { name: 'Report' }).click()
  const questions = page.getByRole('region', { name: 'Questions to ask next' })
  await expect(questions.getByRole('listitem').first()).toContainText('Why did the sponsor pause?')
  await expect(questions.getByText('Expert interview')).toBeVisible()
})

test('with no ranked question the report says so', async ({ page }) => {
  await serve(page)
  await openRun(page, 'divarasib')
  await page.getByRole('link', { name: 'Report' }).click()
  await expect(page.getByText('No question was ranked for this run')).toBeVisible()
})

test('the comparison says which module moved and quotes the evidence that moved it', async ({
  page,
}) => {
  await serve(page)
  await openRun(page, 'divarasib')
  await page.getByRole('link', { name: 'Compare', exact: true }).click()
  await page.getByRole('combobox', { name: 'Earlier run' }).selectOption(OTHER)
  await page.getByRole('button', { name: 'Compare', exact: true }).click()

  const modules = page.getByRole('region', { name: 'Modules' })
  await expect(modules.getByText('(1 of 2 moved)')).toBeVisible()
  const clinical = modules.getByRole('listitem').filter({ hasText: 'Clinical development' })
  await expect(clinical.getByText('Supports the case', { exact: true })).toBeVisible()
  await expect(clinical.getByText('Mixed', { exact: true })).toBeVisible()
  await expect(clinical.getByText('balance +0.61 → +0.12')).toBeVisible()
  await expect(
    clinical.getByText('“no confirmed responses were observed in the expansion cohort”'),
  ).toBeVisible()
  await expect(clinical.getByText('confidence 0.77 → 0.50')).toBeVisible()
  await expect(
    clinical.getByRole('link', { name: 'Open the source: Example congress abstract' }),
  ).toHaveAttribute('href', 'https://www.example.org/abstract/1')
  await expect(modules.getByText('No new evidence reached this module.')).toBeVisible()
})

test('each module gives its answer and opens onto its claims, quotes and sources', async ({
  page,
}) => {
  // The mechanism claims of tests/report.json.
  const claimIds = ['C-0001', 'C-0002', 'C-0003']
  const modules = [
    {
      module: 'mechanism_validation',
      title: 'Mechanism and biological validation',
      question: 'Is the target causal for the disease?',
      answer: 'supports',
      headline: 'The evidence supports the case: favourable weight 0.80 against unfavourable 0.00',
      balance: 1,
      favourable: 0.8,
      unfavourable: 0,
      claim_ids: claimIds,
      drivers: [{ claim_id: 'C-0001', contribution: 0.8 }],
      unknown_count: 1,
      evidence_count: 2,
      gates: [],
    },
    {
      module: 'investment_underwriting',
      title: 'Investment underwriting',
      question: 'Should we invest?',
      answer: 'mixed',
      headline: 'Conditional: gates fired: S1',
      balance: null,
      favourable: 0,
      unfavourable: 0,
      claim_ids: [],
      drivers: [],
      unknown_count: 0,
      evidence_count: 0,
      gates: ['S1'],
    },
  ]
  await serve(page, { report: { ...report, modules } })
  await openRun(page, 'divarasib')
  await page.getByRole('link', { name: 'Report' }).click()

  const scorecard = page.getByRole('region', { name: 'Six modules, six answers' })
  await expect(scorecard.getByText('Supports the case', { exact: true })).toBeVisible()
  await expect(scorecard.getByText('Conditional: gates fired: S1')).toBeVisible()
  await expect(scorecard.getByText('Gate S1 fired')).toBeVisible()
  await scorecard.getByText('Is the target causal for the disease?').click()
  await expect(scorecard.getByText('+0.80 for')).toBeVisible()
  await scorecard
    .getByText('KRAS G12C is a frequent, poor-prognosis driver mutation in NSCLC')
    .click()
  await expect(
    scorecard.getByText(
      '“found in approximately 14% of NSCLC cases and associated with poor prognosis”',
    ),
  ).toBeVisible()
  await expect(
    scorecard.getByRole('link', { name: /Open the original source/ }).first(),
  ).toBeVisible()
})

test('a class landscape lists the drugs of experimental arms, and choosing one prepares its analysis', async ({
  page,
}) => {
  const design = {
    phases: ['PHASE3'],
    armGroups: [
      { label: 'Candidate arm', type: 'EXPERIMENTAL' },
      { label: 'Control arm', type: 'ACTIVE_COMPARATOR' },
    ],
    interventions: [
      { name: 'Synthetic candidate', type: 'DRUG', armGroupLabels: ['Candidate arm'] },
      { name: 'Synthetic comparator', type: 'DRUG', armGroupLabels: ['Control arm'] },
      { name: 'Placebo', type: 'DRUG', armGroupLabels: ['Candidate arm'] },
    ],
  }
  const record = {
    ...evidence[0],
    id: 'E-0001',
    source_family: 'registry',
    url: 'https://clinicaltrials.gov/study/NCT00000001',
    locator: { type: 'nct', value: 'NCT00000001' },
    excerpt: JSON.stringify(design),
  }
  await serve(page, { evidence: [record] })
  await page.goto('/')
  await page.getByLabel('Asset / drug').fill('')
  await page.getByLabel('Indication (optional)').fill('non-small cell lung cancer')
  await page.getByLabel('Mechanism / target (optional)').fill('KRAS G12C inhibitor')
  await page.getByRole('button', { name: 'Run analysis' }).click()

  const choice = page.getByRole('region', { name: 'Choose an existing asset' })
  await expect(choice.getByRole('link', { name: 'NCT00000001' })).toHaveAttribute(
    'href',
    'https://clinicaltrials.gov/study/NCT00000001',
  )
  // A comparator and a placebo are not candidates.
  await expect(choice.getByText('Synthetic comparator')).toHaveCount(0)
  await expect(choice.getByRole('button', { name: /^Select / })).toHaveCount(1)
  await expect(page.getByText('Class landscape for')).toBeVisible()

  await choice.getByRole('button', { name: 'Select Synthetic candidate' }).click()

  await expect(page.getByLabel('Asset / drug')).toHaveValue('Synthetic candidate')
  await expect(page.getByLabel('Indication (optional)')).toHaveValue('non-small cell lung cancer')
  await expect(page.getByLabel('Mechanism / target (optional)')).toHaveValue('KRAS G12C inhibitor')
})

test('a reopened class run is a landscape, not a drug named after its run id', async ({ page }) => {
  await serve(page, { input: { indication: 'multiple sclerosis', mechanism: 'BTK inhibitor' } })
  await page.goto(`/?run=${RUN}#resolved`)

  await expect(page.getByText('Class landscape — select an asset below')).toBeVisible()
  await expect(page.getByRole('region', { name: 'Choose an existing asset' })).toBeVisible()
})
