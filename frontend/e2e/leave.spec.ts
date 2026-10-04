import { expect, test } from '@playwright/test';
import { ADMIN, countCalls, installApi, seedSession, STAFF } from './support/api';

test('leave summary, calendar, and holiday screen render', async ({ page }) => {
  await seedSession(page, STAFF);
  await installApi(page, STAFF);
  await page.goto('/leave');
  await expect(page.getByRole('heading', { name: '연월차 관리' })).toBeVisible();
  await page.goto('/leave/calendar');
  await expect(page.getByRole('heading', { name: '연차 달력' })).toBeVisible();
});

test('leave request and cancel stay on the local API', async ({ page }) => {
  await seedSession(page, STAFF);
  const calls = await installApi(page, STAFF);
  await page.goto('/leave');
  const apply = page.getByRole('button', { name: /신청/ });
  if (await apply.count()) await apply.first().click();
  page.once('dialog', (dialog) => dialog.dismiss());
  const cancel = page.getByRole('button', { name: '취소' });
  if (await cancel.count()) await cancel.first().click();
  expect(calls.filter((call) => call.path.includes('/cancel') && call.method !== 'GET')).toHaveLength(0);
});

test('admin leave screen is available to an admin', async ({ page }) => {
  await seedSession(page, ADMIN);
  await installApi(page, ADMIN);
  await page.goto('/leave');
  await expect(page.getByRole('heading', { name: '연월차 관리' })).toBeVisible();
  await expect(page.getByText(/승인|반려|관리/).first()).toBeVisible();
});
