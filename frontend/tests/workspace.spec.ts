import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  // Opening prepared evidence must not require a provider, backend, or font CDN.
  await page.route('**/*', async (route) => {
    if (new URL(route.request().url()).hostname !== '127.0.0.1') {
      throw new Error('Unexpected external request while opening prepared evidence.')
    }
    await route.continue()
  })
})

async function openEvidence(page: Page, cutoff = '2026-10-07') {
  await page.goto('/')
  await page.getByLabel('Evidence cutoff').fill(cutoff)
  await page.getByRole('button', { name: 'Open analysis' }).click()
  await expect(
    page.getByRole('heading', { name: 'Review the resolved input', exact: true }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Explore evidence' }).click()
  await expect(page.getByRole('heading', { name: 'Evidence explorer', exact: true })).toBeVisible()
}

async function screenshot(page: Page, name: string) {
  const directory = process.env.PLAYWRIGHT_SCREENSHOT_DIR
  if (directory) {
    await mkdir(directory, { recursive: true })
    await page.screenshot({ path: join(directory, `${name}.png`), fullPage: true })
  }
}

test('input → assumptions → exact quote and original source, without external calls', async ({
  page,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/')
  await screenshot(page, 'input-desktop')
  await page.getByLabel('Asset / drug').fill('gdc-6036')
  await page.getByRole('button', { name: 'Open analysis' }).click()
  await expect(
    page.getByRole('heading', { name: 'Review the resolved input', exact: true }),
  ).toBeVisible()
  await expect(page.getByText('Divarasib', { exact: true })).toBeVisible()
  await expect(page.getByText('Assumption', { exact: true }).first()).toBeVisible()
  await screenshot(page, 'resolved-desktop')
  await page.getByRole('button', { name: 'Explore evidence' }).click()
  await expect(page.getByRole('table')).toBeVisible()
  await expect(page.getByRole('status').first()).toContainText('15 of 15 evidence items')
  const detail = page.getByRole('complementary', { name: 'Evidence detail' })
  await expect(detail.getByRole('heading', { name: 'E-0001' })).toBeVisible()
  await expect(detail.locator('blockquote')).toHaveText(
    'The purpose of this study is to assess the safety and efficacy of divarasib compared to locally approved KRAS G12C inhibitors (sotorasib or adagrasib) in participants with KRAS G12C-positive (KRAS G12C +) advanced or metastatic non-small cell lung cancer (NSCLC).',
  )
  await expect(detail.getByRole('link', { name: 'Open original source' })).toHaveAttribute(
    'href',
    'https://clinicaltrials.gov/study/NCT06497556',
  )
  await screenshot(page, 'evidence-desktop')
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await detail.getByRole('button', { name: 'Copy quote' }).click()
  await expect(detail.getByRole('status')).toHaveText('Quote copied.')
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
    await detail.locator('blockquote').textContent(),
  )
  expect(errors).toEqual([])
})

test('unsupported drug gives an actionable error and editing recovers', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Asset / drug').fill('Unknown drug')
  await page.getByRole('button', { name: 'Open analysis' }).click()
  await expect(page.getByRole('alert')).toContainText('This demo supports Divarasib')
  await page.getByLabel('Asset / drug').fill('RG-6330')
  await expect(page.getByRole('alert')).toHaveCount(0)
  await page.getByRole('button', { name: 'Open analysis' }).click()
  await expect(
    page.getByRole('heading', { name: 'Review the resolved input', exact: true }),
  ).toBeVisible()
})

test('filters combine, hidden selection clears, and an empty search can reset', async ({
  page,
}) => {
  await openEvidence(page)
  await page.getByRole('button', { name: 'Select E-0006', exact: true }).click()
  await page.getByRole('combobox', { name: 'Source', exact: true }).selectOption('PubMed')
  await expect(page.getByRole('status').first()).toContainText('7 of 15 evidence items')
  await expect(
    page
      .getByRole('complementary', { name: 'Evidence detail' })
      .getByRole('heading', { name: 'E-0007' }),
  ).toBeVisible()
  await page.getByRole('combobox', { name: 'Source type' }).selectOption('company')
  await expect(page.getByRole('heading', { name: 'No matching evidence' })).toBeVisible()
  await expect(page.getByRole('complementary', { name: 'Evidence detail' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Reset filters' }).click()
  await page.getByLabel('Search evidence').fill('e-0006')
  await expect(page.getByRole('status').first()).toContainText('1 of 15 evidence items')
  await page.getByLabel('Search evidence').fill('no-matching-record')
  await expect(page.getByRole('heading', { name: 'No matching evidence' })).toBeVisible()
  await page.getByRole('button', { name: 'Clear filters' }).click()
  await expect(page.getByRole('status').first()).toContainText('15 of 15 evidence items')
})

test('cutoff excludes later publications and undated records retrieved later', async ({ page }) => {
  await openEvidence(page, '2026-06-30')
  await expect(page.getByRole('status').first()).toContainText('10 of 10 evidence items')
  for (const id of ['E-0003', 'E-0005', 'E-0006', 'E-0014', 'E-0015']) {
    await expect(page.getByRole('button', { name: `Select ${id}`, exact: true })).toHaveCount(0)
  }
  await expect(page.getByRole('button', { name: 'Select E-0007', exact: true })).toBeVisible()
})

test('an empty cutoff directs the user back to inputs, rather than resetting filters', async ({
  page,
}) => {
  await openEvidence(page, '2000-01-01')
  await expect(page.getByRole('heading', { name: 'No evidence by this cutoff' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reset filters' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Review input' }).first().click()
  await page.getByRole('button', { name: 'Back to input' }).click()
  await expect(page.getByLabel('Evidence cutoff')).toHaveValue('2000-01-01')
})

test('sources and keyboard navigation retain the current analysis', async ({ page }) => {
  await openEvidence(page)
  const skip = page.getByRole('link', { name: 'Skip to workspace' })
  await skip.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('main')).toBeFocused()
  await expect(page).toHaveURL(/#evidence$/)
  await page.getByRole('link', { name: 'Sources', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Original sources' })).toBeVisible()
  await page.getByRole('button', { name: 'Select E-0008', exact: true }).focus()
  await page.keyboard.press('Enter')
  await expect(
    page
      .getByRole('complementary', { name: 'Evidence detail' })
      .getByRole('heading', { name: 'E-0008' }),
  ).toBeVisible()
  await page.goBack()
  await expect(page.getByRole('heading', { name: 'Evidence explorer', exact: true })).toBeVisible()
})

test('mobile keeps overflow inside the table and the selected quote readable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await openEvidence(page)
  const width = await page.evaluate(() => ({
    body: document.documentElement.scrollWidth,
    viewport: window.innerWidth,
  }))
  expect(width.body).toBeLessThanOrEqual(width.viewport)
  await page.getByRole('button', { name: 'Select E-0007', exact: true }).click()
  const detail = page.getByRole('complementary', { name: 'Evidence detail' })
  await expect(detail.getByRole('heading', { name: 'E-0007' })).toBeVisible()
  await expect(detail.locator('blockquote')).toBeVisible()
  await screenshot(page, 'evidence-mobile')
})

test('an unavailable demo chunk gives a safe message and a reload action', async ({ page }) => {
  await page.route('**/assets/demo-client-*.js', (route) => route.abort())
  await page.goto('/')
  await page.getByRole('button', { name: 'Open analysis' }).click()
  await expect(page.getByRole('alert')).toContainText('The workspace could not load the demo.')
  await expect(page.getByRole('alert')).not.toContainText('http://')
  await page.unroute('**/assets/demo-client-*.js')
  await page.getByRole('button', { name: 'Reload workspace' }).click()
  await page.getByRole('button', { name: 'Open analysis' }).click()
  await expect(
    page.getByRole('heading', { name: 'Review the resolved input', exact: true }),
  ).toBeVisible()
})
