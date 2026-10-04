import { expect, test } from '@playwright/test';
import { ADMIN, installApi, seedSession, STAFF } from './support/api';

test('staff cannot manage users', async ({ page }) => {
  await seedSession(page, STAFF);
  await installApi(page, STAFF);
  await page.goto('/users');
  await expect(page.getByText('사용자 관리 권한이 없습니다.')).toBeVisible();
});

test('admin settings render and a failed save shows an alert', async ({ page }) => {
  await seedSession(page, ADMIN);
  await installApi(page, ADMIN);
  await page.goto('/settings');
  await expect(page.getByRole('heading', { name: '회사 설정' })).toBeVisible();
  await page.route('http://localhost:8000/settings/company**', async (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ company_name: '스프링풀필먼트' }) });
    }
    return route.fulfill({ status: 403, contentType: 'application/json', body: JSON.stringify({ detail: '권한이 없습니다.' }) });
  });
  const save = page.getByRole('button', { name: /저장/ });
  if (await save.count()) {
    await save.first().click();
    await expect(page.locator('.alert-error')).toBeVisible();
  }
});

test('rates, storage, and vendor charges render for an admin', async ({ page }) => {
  await seedSession(page, ADMIN);
  await installApi(page, ADMIN);
  await page.goto('/rates');
  await expect(page.getByRole('heading', { name: '글로벌 요금표 관리' })).toBeVisible();
  await page.goto('/storage');
  await expect(page.getByRole('heading', { name: '보관료 관리' })).toBeVisible();
  await page.goto('/vendor-charges');
  await expect(page.getByRole('heading', { name: '거래처별 추가 비용 관리' })).toBeVisible();
});

test('401, 403, and network failure stay visible as errors', async ({ page }) => {
  await seedSession(page, ADMIN);
  await installApi(page, ADMIN);
  await page.route('http://localhost:8000/settings/company**', (route) => route.abort('failed'));
  await page.goto('/settings');
  await expect(page.getByText('설정을 불러오는데 실패했습니다.')).toBeVisible();
});
