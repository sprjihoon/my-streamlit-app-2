import { expect, test } from '@playwright/test';
import { ADMIN, countCalls, installApi, seedSession, STAFF } from './support/api';

test('login screen renders', async ({ page }) => {
  await page.goto('/login');
  await expect(page.getByRole('heading', { name: '틸리언' })).toBeVisible();
  await expect(page.getByRole('button', { name: '로그인' })).toBeVisible();
  await expect(page.locator('aside.sidebar')).toHaveCount(0);
});

test('empty login does not call the API', async ({ page }) => {
  const calls = await installApi(page, STAFF);
  await page.goto('/login');
  await page.getByRole('button', { name: '로그인' }).click();
  await expect(page.getByText('아이디와 비밀번호를 입력하세요.')).toBeVisible();
  expect(countCalls(calls, 'POST', '/auth/login')).toBe(0);
});

test('wrong password shows the API error', async ({ page }) => {
  await installApi(page, STAFF);
  await page.goto('/login');
  await page.getByPlaceholder('아이디 입력').fill('staff');
  await page.getByPlaceholder('비밀번호 입력').fill('wrong');
  await page.getByRole('button', { name: '로그인' }).click();
  await expect(page.getByText('아이디 또는 비밀번호가 올바르지 않습니다.')).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test('successful login opens the app', async ({ page }) => {
  await installApi(page, ADMIN);
  await page.goto('/login');
  await page.getByPlaceholder('아이디 입력').fill('admin');
  await page.getByPlaceholder('비밀번호 입력').fill('secret');
  await page.getByRole('button', { name: '로그인' }).click();
  await expect(page.getByRole('heading', { name: '대시보드' })).toBeVisible();
});

test('admin and staff menus differ', async ({ page }) => {
  await seedSession(page, ADMIN);
  await installApi(page, ADMIN);
  await page.goto('/');
  await page.getByRole('button', { name: '관리자', exact: true }).click();
  await expect(page.getByRole('link', { name: '사용자 관리' })).toBeVisible();
  await expect(page.getByRole('link', { name: '대시보드' })).toBeVisible();

  await page.evaluate(() => localStorage.clear());
  await seedSession(page, STAFF);
  await installApi(page, STAFF);
  await page.goto('/insights');
  await expect(page.getByRole('heading', { name: '데이터 인사이트' })).toBeVisible();
  await expect(page.getByRole('link', { name: '사용자 관리' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: '대시보드' })).toHaveCount(0);
});

test('logout returns to login', async ({ page }) => {
  await seedSession(page, STAFF);
  const calls = await installApi(page, STAFF);
  await page.goto('/insights');
  await page.getByRole('button', { name: '로그아웃' }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(countCalls(calls, 'POST', '/auth/logout')).toBe(1);
});

test('password modal opens and closes', async ({ page }) => {
  await seedSession(page, STAFF);
  await installApi(page, STAFF);
  await page.goto('/insights');
  await page.getByRole('button', { name: '비밀번호' }).click();
  await expect(page.getByRole('heading', { name: '비밀번호 변경' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('heading', { name: '비밀번호 변경' })).toBeVisible();
  await page.getByRole('button', { name: '취소' }).click();
  await expect(page.getByRole('heading', { name: '비밀번호 변경' })).toHaveCount(0);
});

test('forced password change cannot be dismissed', async ({ page }) => {
  await seedSession(page, STAFF, true);
  await installApi(page, STAFF);
  await page.goto('/insights');
  await expect(page.getByRole('heading', { name: '비밀번호 변경 필요' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('heading', { name: '비밀번호 변경 필요' })).toBeVisible();
  await expect(page.getByRole('button', { name: '취소' })).toHaveCount(0);
});

test('expired session redirects to login', async ({ page }) => {
  await seedSession(page, STAFF);
  await page.route('http://localhost:8000/auth/me**', (route) =>
    route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: '로그인이 필요합니다.' }) }),
  );
  await page.goto('/work-log');
  await expect(page).toHaveURL(/\/login$/);
});
