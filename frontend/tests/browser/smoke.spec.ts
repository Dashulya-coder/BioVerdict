import { expect, test } from '@playwright/test'

// This verifies the current starter and the browser harness, not a report flow.
// Replace it with product behavior assertions when the real UI lands.
test('starter renders and responds without runtime errors', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Get started' })).toBeVisible()
  await page.getByRole('button', { name: 'Count is 0', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Count is 1', exact: true })).toBeVisible()
  expect(errors).toEqual([])
})
