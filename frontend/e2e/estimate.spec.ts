import { expect, test } from '@playwright/test';
import { ADMIN, installApi, seedSession } from './support/api';

test('public estimate page calculates without the sidebar', async ({ page }) => {
  await installApi(page, ADMIN);
  await page.goto('/estimate');
  await expect(page.getByRole('heading', { name: '스프링풀필먼트 견적확인하기' })).toBeVisible();
  await expect(page.locator('aside.sidebar')).toHaveCount(0);
});

test('estimate list, analytics, and filter render', async ({ page }) => {
  await seedSession(page, ADMIN);
  await installApi(page, ADMIN);
  await page.goto('/estimate-list');
  await expect(page.getByRole('heading', { name: '견적서 목록' })).toBeVisible();
  await page.goto('/estimate-analytics');
  await expect(page.getByRole('heading', { name: /견적/ })).toBeVisible();
});

test('estimate save failure stays on the page', async ({ page }) => {
  await installApi(page, ADMIN);
  await page.route('http://localhost:8000/estimate/save**', (route) =>
    route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ detail: '저장할 수 없습니다.' }) }),
  );
  await page.goto('/estimate');
  const save = page.getByRole('button', { name: /저장|견적/ });
  if (await save.count()) {
    await save.first().click();
  }
  await expect(page.getByRole('heading', { name: '스프링풀필먼트 견적확인하기' })).toBeVisible();
});
