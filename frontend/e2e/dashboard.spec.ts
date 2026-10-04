import { expect, test } from '@playwright/test';
import { ADMIN, installApi, seedSession } from './support/api';

test.beforeEach(async ({ page }) => {
  await seedSession(page, ADMIN);
});

test('dashboard shows health and uploads', async ({ page }) => {
  await installApi(page, ADMIN);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '대시보드' })).toBeVisible();
  await expect(page.getByText('ok · vtest')).toBeVisible();
  await expect(page.getByText('입고.xlsx')).toBeVisible();
});

test('dashboard empty upload state', async ({ page }) => {
  await installApi(page, ADMIN);
  await page.route('http://localhost:8000/upload/list**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, uploads: [] }) }),
  );
  await page.goto('/');
  await expect(page.getByText('업로드된 파일이 없습니다.')).toBeVisible();
  await expect(page.locator('.alert-error')).toHaveCount(0);
});

test('dashboard distinguishes API failure from empty data', async ({ page }) => {
  await installApi(page, ADMIN);
  await page.route('http://localhost:8000/health**', (route) => route.abort('failed'));
  await page.goto('/');
  await expect(page.locator('.alert-error')).toContainText('서버에 연결할 수 없습니다');
});

test('dashboard 500 is not shown as an empty list', async ({ page }) => {
  await installApi(page, ADMIN);
  await page.route('http://localhost:8000/health**', (route) =>
    route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: '서버 오류' }) }),
  );
  await page.goto('/');
  await expect(page.locator('.alert-error')).toBeVisible();
});

test('quick action opens the return request page', async ({ page }) => {
  await installApi(page, ADMIN);
  await page.goto('/');
  await page.locator('main').getByRole('link', { name: '회수신청' }).click();
  await expect(page.getByRole('heading', { name: '회수신청', exact: true })).toBeVisible();
});
