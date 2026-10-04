import { expect, test } from '@playwright/test';
import { ADMIN, installApi, seedSession } from './support/api';

test.beforeEach(async ({ page }) => {
  await seedSession(page, ADMIN);
  await installApi(page, ADMIN);
});

test('inbound list, overview, and share shell', async ({ page }) => {
  await page.goto('/inbound-log');
  await expect(page.getByRole('heading', { name: '입고일지' })).toBeVisible();
  await page.goto('/inbound-overview');
  await expect(page.getByRole('heading', { name: '통합 현황' })).toBeVisible();
  await page.goto('/share/demo-token');
  await expect(page.locator('aside.sidebar')).toHaveCount(0);
});

test('inbound item and photo endpoints are not called until the user asks', async ({ page }) => {
  const calls = await installApi(page, ADMIN);
  await page.goto('/inbound-log');
  await expect(page.getByRole('heading', { name: '입고일지' })).toBeVisible();
  expect(calls.some((call) => call.path.includes('/ocr-preview'))).toBe(false);
  expect(calls.some((call) => call.method === 'PATCH')).toBe(false);
  expect(calls.some((call) => call.path.includes('/close'))).toBe(false);
});

test('closing and grading buttons are absent on an empty inbound list', async ({ page }) => {
  await page.goto('/inbound-log');
  await expect(page.getByRole('button', { name: '마감' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '양품화' })).toHaveCount(0);
});
