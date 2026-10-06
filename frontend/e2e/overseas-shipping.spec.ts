import { expect, test } from '@playwright/test';
import { countCalls, installApi, seedSession, STAFF } from './support/api';

test.beforeEach(async ({ page }) => {
  await seedSession(page, STAFF);
  await installApi(page, STAFF);
});

test('sender, recipient, HS, quote, and preview stay on the test API', async ({ page }) => {
  const calls = await installApi(page, STAFF);
  await page.goto('/overseas-shipping');
  await expect(page.getByRole('heading', { name: '해외배송 접수' })).toBeVisible();
  await expect(page.getByRole('button', { name: '상품', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '선물' })).toBeVisible();
  await expect(page.getByRole('button', { name: '상품견본' })).toBeVisible();
  await page.getByRole('button', { name: '선물' }).click();
  await expect.poll(() => calls.some((call) => call.path === '/overseas-shipping/quote' && (call.search || '').includes('customs_gubun=gift'))).toBeTruthy();
  await page.getByRole('button', { name: '상품견본' }).click();
  await expect.poll(() => calls.some((call) => call.path === '/overseas-shipping/quote' && (call.search || '').includes('customs_gubun=sample'))).toBeTruthy();
  await expect.poll(() => calls.some((call) => call.method === 'GET' && call.path === '/overseas-shipping/quote')).toBeTruthy();
  await expect(page.locator('input[value="Taro"], input[value="스프링"]').first()).toBeVisible();
  await expect(page.getByText('USD 150.00 × 17%')).toBeVisible();
  await expect(page.getByText('USD 31.9990 × 1,400원 × 1.02')).toBeVisible();
  await expect(page.getByText('46,000원').first()).toBeVisible();
});

test('create failure and success do not leave the browser', async ({ page }) => {
  const calls = await installApi(page, STAFF);
  await page.goto('/overseas-shipping');
  page.on('dialog', (dialog) => dialog.accept());
  await page.route('http://localhost:8000/overseas-shipping**', async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === 'POST' && (url.pathname === '/overseas-shipping' || url.pathname === '/overseas-shipping/preview')) {
      return route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ detail: 'EMS 응답 없음' }) });
    }
    return route.fallback();
  });
  await page.getByRole('button', { name: '테스트 접수' }).click();
  await expect(page.getByText('EMS 응답 없음')).toBeVisible();

  await page.unroute('http://localhost:8000/overseas-shipping**');
  await page.getByRole('button', { name: '테스트 접수' }).click();
  await expect(page.getByText('EG123456789KR')).toBeVisible();
  expect(countCalls(calls, 'POST', '/overseas-shipping')).toBeGreaterThan(0);
  expect(calls.some((call) => /fedex|epost\.go\.kr/i.test(call.path))).toBe(false);
});

test('list, detail, cancel dismissal, and print link', async ({ page }) => {
  const calls = await installApi(page, STAFF);
  await page.goto('/overseas-shipping-list');
  await expect(page.getByRole('heading', { name: '해외배송 접수목록' })).toBeVisible();
  await page.goto('/overseas-shipping-list/9');
  await expect(page.getByRole('heading', { name: '해외배송 접수 상세' })).toBeVisible();
  const print = page.getByRole('link', { name: /출력|인쇄/ });
  if (await print.count()) {
    await expect(print.first()).toHaveAttribute('href', /overseas-print|label/);
  }
  page.once('dialog', (dialog) => dialog.dismiss());
  const cancel = page.getByRole('button', { name: /취소/ });
  if (await cancel.count()) await cancel.first().click();
  expect(calls.filter((call) => call.path.includes('/cancel'))).toHaveLength(0);
});
