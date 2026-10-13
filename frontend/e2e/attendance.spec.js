import { expect, test } from '@playwright/test';

// Read-only regression suite for regularization prefill + analytics rendering.
// Prerequisite: backend API on http://127.0.0.1:8000 with seed data.

test.beforeEach(async ({ page }) => {
  await page.goto('/', { waitUntil: 'networkidle' });
  await expect(page.getByText('Page 1 of 1')).toBeVisible({ timeout: 15000 });
  await page.getByRole('button', { name: 'Attendance', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Fix', exact: true }).first()).toBeVisible({ timeout: 15000 });
});

test('Fix prefills punch times as datetime-local values', async ({ page }) => {
  await page.getByRole('button', { name: 'Fix', exact: true }).first().click();
  const vals = await page.locator('input[type="datetime-local"]').evaluateAll(
    (els) => els.map((e) => e.value),
  );
  expect(vals).toHaveLength(2);
  for (const v of vals) expect(v).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
});
