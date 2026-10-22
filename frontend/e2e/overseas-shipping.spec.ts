import { expect, test, type Page } from '@playwright/test';
import { countCalls, installApi, seedSession, ADMIN, STAFF } from './support/api';

async function liveOverseasMeta(page: Page) {
  await page.route('http://localhost:8000/overseas-shipping/meta**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        live_ready: true,
        methods: [{ code: 'EMS', name: 'EMS', desc: 'EMS', premiumcd: '31', em_ee: 'em' }],
        sender: { name: '스프링', addr: '대구', zip: '41940', addr1: 'Daegu', addr2: 'Jung', addr3: '394', tel: '01012345678' },
        item_categories: [],
        saved_hs: [],
      }),
    });
  });
}

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

test('staff live intake has no test checkbox and posts a real receipt', async ({ page }) => {
  const calls = await installApi(page, STAFF);
  await liveOverseasMeta(page);
  await page.goto('/overseas-shipping');
  await expect(page.getByRole('heading', { name: '해외배송 접수' })).toBeVisible();
  await expect(page.getByRole('checkbox', { name: /테스트 접수/ })).toHaveCount(0);
  page.on('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: '해외배송 접수' }).click();
  await expect(page.getByText('EG123456789KR')).toBeVisible();
  const post = calls.find((call) => call.method === 'POST' && call.path === '/overseas-shipping');
  expect(post?.body && JSON.parse(post.body).test_mode).toBe(false);
});

test('admin can still choose a test receipt', async ({ page }) => {
  await seedSession(page, ADMIN);
  const calls = await installApi(page, ADMIN);
  await liveOverseasMeta(page);
  await page.goto('/overseas-shipping');
  await expect(page.getByRole('checkbox', { name: /테스트 접수/ })).toBeVisible();
  await page.getByRole('checkbox', { name: /테스트 접수/ }).check();
  page.on('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: '테스트 접수' }).click();
  await expect(page.getByText('EG123456789KR')).toBeVisible();
  const post = calls.find((call) => call.method === 'POST' && call.path === '/overseas-shipping');
  expect(post?.body && JSON.parse(post.body).test_mode).toBe(true);
});

test('delivered list row has no cancel button', async ({ page }) => {
  await installApi(page, STAFF);
  await page.route('http://localhost:8000/overseas-shipping**', async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === 'GET' && (url.pathname === '/overseas-shipping' || url.pathname === '/overseas-shipping/11')) {
      const item = {
        id: 11,
        order_no: 'TIL-11',
        tracking_no: 'EG999000111KR',
        sender_name: 'reindeer',
        recipient_name: 'Done',
        countrycd: 'JP',
        shipping_method: 'EMS',
        status: 'requested',
        is_test: false,
        treat_status: '배달완료',
        treat_status_name: '배달완료',
        created_by: '물류담당',
        ems_fee: '18000',
        created_at: '2026-10-08T09:00:00',
        items: [],
      };
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(url.pathname === '/overseas-shipping' ? { items: [item] } : item),
      });
    }
    return route.fallback();
  });
  await page.goto('/overseas-shipping-list');
  await expect(page.getByRole('cell', { name: '배달완료' })).toBeVisible();
  await expect(page.getByRole('button', { name: '접수 취소' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: '출력서류' })).toBeVisible();
  await expect(page.getByRole('button', { name: '재접수' })).toBeVisible();
  await page.goto('/overseas-shipping-list/11');
  await expect(page.getByRole('heading', { name: '해외배송 접수 상세' })).toBeVisible();
  await expect(page.getByRole('button', { name: '접수 취소' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: '출력서류' })).toBeVisible();
});

test('list filters, paging, and resubmit from a saved row', async ({ page }) => {
  await installApi(page, STAFF);
  let resubmitted = false;
  await page.route('http://localhost:8000/overseas-shipping/**', async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === 'POST' && url.pathname === '/overseas-shipping/9/resubmit') {
      resubmitted = true;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          id: 12,
          order_no: 'TIL-12',
          tracking_no: 'EG555000111KR',
          ems_fee: '18000',
          is_test: false,
        }),
      });
    }
    return route.fallback();
  });
  await page.goto('/overseas-shipping-list');
  await expect(page.getByRole('cell', { name: 'Taro' })).toBeVisible();
  await page.getByLabel('상태').selectOption('canceled');
  await expect(page.getByText('검색 결과가 없습니다.')).toBeVisible();
  await page.getByRole('button', { name: '초기화' }).click();
  await expect(page.getByRole('cell', { name: 'Taro' })).toBeVisible();
  await expect(page.getByLabel('페이지당')).toBeVisible();
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: '재접수' }).click();
  await expect(page.getByText('재접수 완료. 등기번호 EG555000111KR')).toBeVisible();
  expect(resubmitted).toBe(true);
});

test('list, detail, cancel dismissal, and print link', async ({ page }) => {
  const calls = await installApi(page, STAFF);
  await page.goto('/overseas-shipping-list');
  await expect(page.getByRole('heading', { name: '해외배송 접수목록' })).toBeVisible();
  await expect(page.getByRole('cell', { name: '테스트' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'reindeer' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'Taro' })).toBeVisible();
  await page.getByRole('button', { name: '복사' }).click();
  await expect(page.getByText('복사했습니다.')).toBeVisible();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe('EG123456789KR');
  await expect(page).toHaveURL(/\/overseas-shipping-list$/);
  await page.getByRole('button', { name: '송장조회' }).click();
  await expect(page.getByText('등기 1건 조회. 배달완료 0건')).toBeVisible();
  await expect(page.getByRole('cell', { name: '운송중' })).toBeVisible();
  expect(calls.filter((call) => call.method === 'POST' && call.path === '/overseas-shipping/refresh-status')).toHaveLength(1);
  await page.goto('/overseas-shipping-list/9');
  await expect(page.getByRole('heading', { name: '해외배송 접수 상세' })).toBeVisible();
  await expect(page.getByRole('textbox', { name: '배송상태' })).toHaveValue('운송중');
  await expect(page.getByRole('textbox', { name: '최근 처리' })).toHaveValue('교환국 도착 · 국제우편물류센터 · 2026.10.08 09:10');
  const print = page.getByRole('link', { name: /출력|인쇄/ });
  if (await print.count()) {
    await expect(print.first()).toHaveAttribute('href', /overseas-print|label/);
  }
  page.once('dialog', (dialog) => dialog.dismiss());
  const cancel = page.getByRole('button', { name: /취소/ });
  if (await cancel.count()) await cancel.first().click();
  expect(calls.filter((call) => call.path.includes('/cancel'))).toHaveLength(0);
});
