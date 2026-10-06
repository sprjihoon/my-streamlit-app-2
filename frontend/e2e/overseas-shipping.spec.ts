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
  const pane = page.locator('.overseas-invoice-scroll');
  const paneMetrics = await pane.evaluate((el) => {
    const style = getComputedStyle(el);
    return {
      overflowX: style.overflowX,
      overflowY: style.overflowY,
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
      scrollHeight: el.scrollHeight,
      clientHeight: el.clientHeight,
    };
  });
  expect(paneMetrics.overflowX).toBe('visible');
  expect(paneMetrics.overflowY).toBe('visible');
  expect(paneMetrics.scrollWidth).toBeLessThanOrEqual(paneMetrics.clientWidth + 1);
  expect(paneMetrics.scrollHeight).toBeLessThanOrEqual(paneMetrics.clientHeight + 1);
  await page.getByRole('textbox', { name: '1행 HS코드' }).fill('610910');
  await page.getByRole('textbox', { name: '1행 품목' }).focus();
  const menu = page.locator('.overseas-hs-menu');
  await expect(menu).toBeVisible();
  const menuMetrics = await menu.evaluate((el) => ({
    overflowX: getComputedStyle(el).overflowX,
    scrollWidth: el.scrollWidth,
    clientWidth: el.clientWidth,
  }));
  expect(menuMetrics.overflowX).toBe('hidden');
  expect(menuMetrics.scrollWidth).toBeLessThanOrEqual(menuMetrics.clientWidth + 1);
  await expect(page.getByRole('button', { name: '상품', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '선물' })).toBeVisible();
  await expect(page.getByRole('button', { name: '상품견본' })).toBeVisible();
  await page.getByRole('button', { name: '선물' }).click();
  await expect.poll(() => calls.some((call) => call.path === '/overseas-shipping/quote' && (call.search || '').includes('customs_gubun=gift'))).toBeTruthy();
  await page.getByRole('button', { name: '상품견본' }).click();
  await expect.poll(() => calls.some((call) => call.path === '/overseas-shipping/quote' && (call.search || '').includes('customs_gubun=sample'))).toBeTruthy();
  await expect.poll(() => calls.some((call) => call.method === 'GET' && call.path === '/overseas-shipping/quote')).toBeTruthy();
  await expect(page.locator('input[value="Taro"], input[value="스프링"]').first()).toBeVisible();
  await expect(page.getByText('USD 150.00 × 16.5%')).toBeVisible();
  await expect(page.getByText('USD 28.6165 × 1,400원')).toBeVisible();
  await expect(page.getByText('40,063원').first()).toBeVisible();
  const finalRow = page.locator('.fee-line.is-ddp-final');
  await expect(finalRow).toContainText('청구액');
  await expect(finalRow).toContainText('40,063원');
  const applied = page.locator('.fee-meta-volume');
  await expect(applied).toContainText('적용 부피');
  await expect(applied).toHaveCSS('color', 'rgb(180, 83, 9)');
  const colors = await page.evaluate(() => {
    const finalAmount = document.querySelector('.fee-line.is-ddp-final strong');
    const step = document.querySelector('.fee-line.is-sub:not(.is-ddp-final)');
    return {
      final: finalAmount ? getComputedStyle(finalAmount).color : '',
      step: step ? getComputedStyle(step).color : '',
    };
  });
  expect(colors.final).not.toBe(colors.step);
  expect(colors.final).toBe('rgb(67, 97, 238)');
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
