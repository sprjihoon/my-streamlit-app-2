import { expect, test } from '@playwright/test';
import { installApi, seedSession, STAFF } from './support/api';

test.beforeEach(async ({ page }) => {
  await seedSession(page, STAFF);
  await installApi(page, STAFF);
});

async function fits(page: import('@playwright/test').Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThan(24);
}

test('mobile login has no horizontal overflow', async ({ page }) => {
  await page.goto('/login');
  await expect(page.getByRole('button', { name: '로그인' })).toBeVisible();
  const box = await page.getByRole('button', { name: '로그인' }).boundingBox();
  expect(box && box.x >= 0 && box.x + box.width <= 400).toBeTruthy();
  await fits(page);
});

test('mobile domestic form keeps the submit button reachable', async ({ page }) => {
  await page.goto('/domestic-shipping');
  const button = page.getByRole('button', { name: '접수', exact: true });
  await expect(button).toBeVisible();
  await button.scrollIntoViewIfNeeded();
  const box = await button.boundingBox();
  expect(box && box.width > 20).toBeTruthy();
  await fits(page);
});

test('mobile pickup form keeps the submit button reachable', async ({ page }) => {
  await page.goto('/return-request');
  const button = page.getByRole('button', { name: '테스트 접수' });
  await expect(button).toBeVisible();
  await button.scrollIntoViewIfNeeded();
  await fits(page);
});

test('mobile inbound work page has no desktop sidebar', async ({ page }) => {
  await page.goto('/inbound/1');
  await expect(page.locator('aside.sidebar')).toHaveCount(0);
  const dialog = page.getByRole('dialog');
  if (await dialog.count()) {
    await expect(dialog.first()).toBeVisible();
  }
});
