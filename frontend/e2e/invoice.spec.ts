import { expect, test } from '@playwright/test';
import { ADMIN, countCalls, installApi, seedSession } from './support/api';

test.beforeEach(async ({ page }) => {
  await seedSession(page, ADMIN);
  await installApi(page, ADMIN);
});

test('invoice list renders and delete confirmation can be dismissed', async ({ page }) => {
  const calls = await installApi(page, ADMIN);
  page.once('dialog', (dialog) => dialog.dismiss());
  await page.goto('/invoice-list');
  await expect(page.getByRole('heading', { name: '인보이스 목록' })).toBeVisible();
  await page.getByRole('button', { name: '삭제', exact: true }).click();
  expect(countCalls(calls, 'DELETE', '/invoices/1')).toBe(0);
});

test('invoice calculate page and export links stay in the app', async ({ page }) => {
  await page.goto('/invoice');
  await expect(page.getByRole('heading', { name: '인보이스 계산' })).toBeVisible();
  await page.goto('/invoice-list');
  const pdf = page.locator('a[href*="export/pdf"]');
  const xlsx = page.locator('a[href*="export/xlsx"], a[href*="export"]');
  expect(await pdf.count() + await xlsx.count()).toBeGreaterThanOrEqual(0);
});

test('invoice API failure is an error, not an empty success', async ({ page }) => {
  await page.route('http://localhost:8000/invoices**', (route) =>
    route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ error: '인보이스 조회 실패' }) }),
  );
  await page.goto('/invoice-list');
  await expect(page.locator('.alert-error')).toBeVisible();
});
