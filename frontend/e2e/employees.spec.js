import { expect, test } from '@playwright/test';

// Read-only regression suite for the Employees search flow.
// Prerequisite: backend API on http://127.0.0.1:8000 with seed data
// (6 employees across Engineering/Sales/Support).
// Run: npm run test:e2e

test.beforeEach(async ({ page }) => {
  await page.goto('/', { waitUntil: 'networkidle' });
  await expect(page.getByText('Page 1 of 1')).toBeVisible({ timeout: 15000 });
});

async function searchDept(page, q) {
  await page.locator('form').first().locator('input').first().fill(q);
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  // eslint-disable-next-line no-promise-executor-return
  await page.waitForTimeout(1200);
}

async function rowTexts(page) {
  return page.locator('table tbody tr').allInnerTexts();
}

test('search Sales shows only Sales with filtered total', async ({ page }) => {
  await searchDept(page, 'Sales');
  const rows = await rowTexts(page);
  expect(rows).toHaveLength(2);
  for (const r of rows) expect(r).toContain('Sales');
  await expect(page.locator('main').getByText('2 total')).toBeVisible();
});

test('search Engineering, then clear restores all', async ({ page }) => {
  await searchDept(page, 'Engineering');
  let rows = await rowTexts(page);
  expect(rows).toHaveLength(2);
  for (const r of rows) expect(r).toContain('Engineering');
  await searchDept(page, '');
  rows = await rowTexts(page);
  expect(rows).toHaveLength(6);
});

test('unknown department shows empty state without stale rows', async ({ page }) => {
  await searchDept(page, 'NoSuchDept');
  expect(await rowTexts(page)).toHaveLength(0);
  await expect(page.locator('main').getByText('No records found.')).toBeVisible();
});

test('lowercase query respects exact-match contract', async ({ page }) => {
  await searchDept(page, 'sales');
  expect(await rowTexts(page)).toHaveLength(0);
  await expect(page.locator('main').getByText('No records found.')).toBeVisible();
});

test('failed search shows error and clears stale rows', async ({ page }) => {
  await page.route('**/employees*', (route) => route.abort());
  await searchDept(page, 'Sales');
  await expect(page.locator('main').getByText(/Error:/)).toBeVisible();
  expect(await rowTexts(page)).toHaveLength(0);
});
