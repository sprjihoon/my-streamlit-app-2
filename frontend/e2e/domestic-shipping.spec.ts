import { expect, test } from '@playwright/test';
import { countCalls, installApi, seedSession, STAFF } from './support/api';

test.beforeEach(async ({ page }) => {
  await seedSession(page, STAFF);
  await installApi(page, STAFF);
});

async function fillDomestic(page: import('@playwright/test').Page) {
  await page.goto('/domestic-shipping');
  await expect(page.getByText('우체국 연결이 없어 테스트로 저장됩니다.')).toBeVisible();
  await expect(page.locator('#box_size')).toHaveValue('MICRO');
  await page.locator('#vendor_id').selectOption('1');
  await page.locator('#print_sender_name').fill('보내는사람');
  await page.locator('#print_sender_phone').fill('01011112222');
  await page.getByRole('button', { name: '직접 입력' }).first().click();
  await page.locator('#print_sender_zip').fill('41940');
  await page.locator('#print_sender_addr1').fill('대구 중구 중앙대로 394');
  await page.locator('#print_sender_addr2').fill('2층');
  await page.locator('#saved_recipient').selectOption('3');
  await expect(page.locator('#recipient_name')).toHaveValue('홍길동');
  await page.locator('#recipient_addr2').fill('101호');
}

test('required fields block submit', async ({ page }) => {
  const calls = await installApi(page, STAFF);
  await page.goto('/domestic-shipping');
  await page.getByRole('button', { name: '접수', exact: true }).click();
  await expect(page.locator('#vendor_id-error')).toHaveText('업체를 선택해주세요.');
  expect(countCalls(calls, 'POST', '/domestic-shipping')).toBe(0);
});

test('address search fallback keeps manual entry', async ({ page }) => {
  await page.goto('/domestic-shipping');
  await page.getByRole('button', { name: '주소 검색' }).first().click();
  await expect(page.getByText('주소 검색을 불러오지 못했습니다.')).toBeVisible();
  await expect(page.locator('#print_sender_zip')).toBeEditable();
});

test('saved address, success, and failed submit keep the form', async ({ page }) => {
  const paths: string[] = [];
  page.on('request', (request) => {
    paths.push(new URL(request.url()).pathname);
  });
  await fillDomestic(page);
  expect(paths).toContain('/domestic-shipping/saved-recipients');
  expect(paths).not.toContain('/kpost-pickup/saved-recipients');
  await page.getByRole('button', { name: '접수', exact: true }).click();
  await expect(page.getByRole('heading', { name: '테스트 접수' })).toBeVisible();
  await page.getByRole('button', { name: '취소' }).click();
  await expect(page.getByRole('heading', { name: '테스트 접수' })).toHaveCount(0);

  await page.route('http://localhost:8000/domestic-shipping**', async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === 'POST' && url.pathname === '/domestic-shipping') {
      return route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ detail: '우체국 응답 없음' }) });
    }
    return route.fallback();
  });
  await page.getByRole('button', { name: '접수', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '접수' }).click();
  await expect(page.getByText('입력한 내용은 그대로입니다.')).toBeVisible();
  await expect(page.locator('#recipient_name')).toHaveValue('홍길동');

  await page.unroute('http://localhost:8000/domestic-shipping**');
  await page.getByRole('button', { name: '접수', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '접수' }).click();
  await expect(page.getByText('D-100')).toBeVisible();
});

test('duplicate confirm does not send a second create', async ({ page }) => {
  let posts = 0;
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (request.method() === 'POST' && url.pathname === '/domestic-shipping') posts += 1;
  });
  await installApi(page, STAFF);
  await page.route('http://localhost:8000/domestic-shipping**', async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === 'POST' && url.pathname === '/domestic-shipping') {
      await new Promise((resolve) => setTimeout(resolve, 600));
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, id: 7, order_no: 'D-100', tracking_no: '1234567890123', is_test: true }),
      });
    }
    return route.fallback();
  });
  await fillDomestic(page);
  await page.getByRole('button', { name: '접수', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '접수' }).click();
  await expect(page.getByRole('dialog').getByText('접수 중...')).toBeVisible();
  await expect(page.getByText('D-100')).toBeVisible();
  expect(posts).toBe(1);
});

test('list filter, detail copy, and cancel dismissal', async ({ page }) => {
  const calls = await installApi(page, STAFF);
  await page.goto('/domestic-shipping-list');
  await expect(page.getByText('1234567890123')).toBeVisible();
  await expect(page.getByText('1–1 / 1건')).toBeVisible();
  await expect(page.getByRole('combobox', { name: '페이지당' })).toHaveValue('30');
  await page.getByRole('combobox', { name: '상태' }).selectOption('canceled');
  await expect(page.getByText('검색 결과가 없습니다.')).toBeVisible();
  await page.getByRole('button', { name: '초기화' }).click();
  await page.getByRole('button', { name: '송장조회' }).click();
  await expect(page.getByText('송장 1건 조회. 배달완료 1건')).toBeVisible();
  await expect(page.getByRole('cell', { name: '배달완료' })).toBeVisible();
  expect(calls.filter((call) => call.method === 'POST' && call.path === '/domestic-shipping/refresh-status')).toHaveLength(1);
  await page.getByRole('button', { name: '접수 취소' }).click();
  await page.getByRole('dialog').getByRole('button', { name: '취소', exact: true }).first().click();
  expect(calls.filter((call) => call.path.includes('/cancel'))).toHaveLength(0);
  await page.goto('/domestic-shipping-list/7');
  await expect(page.getByRole('heading', { name: '홍길동' })).toBeVisible();
  await page.getByRole('button', { name: '복사' }).click();
  await expect(page.getByText('복사했습니다.')).toBeVisible();
  await page.getByRole('link', { name: '목록으로' }).click();
  await expect(page.getByRole('heading', { name: '출고 목록' })).toBeVisible();
});

test('list pages thirty rows and returns to the first page on search', async ({ page }) => {
  await page.route('http://localhost:8000/domestic-shipping**', async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === 'GET' && url.pathname === '/domestic-shipping') {
      const items = Array.from({ length: 31 }, (_, index) => ({
        id: index + 1,
        vendor_id: 1,
        vendor_name: '스프링',
        recipient_name: `수취${index + 1}`,
        tracking_no: `T${String(index + 1).padStart(12, '0')}`,
        order_no: `D-${index + 1}`,
        price: '3500',
        status: 'requested',
        is_test: true,
        created_by: '물류담당',
        created_at: '2026-10-04T09:00:00',
      }));
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items }) });
    }
    return route.fallback();
  });
  await page.goto('/domestic-shipping-list');
  await expect(page.getByText('1–30 / 31건')).toBeVisible();
  await expect(page.getByText('T000000000001')).toBeVisible();
  await expect(page.getByText('T000000000031')).toHaveCount(0);
  await page.getByRole('button', { name: '2', exact: true }).click();
  await expect(page.getByText('31–31 / 31건')).toBeVisible();
  await expect(page.getByText('T000000000031')).toBeVisible();
  await expect(page.getByText('T000000000001')).toHaveCount(0);
  await page.getByRole('textbox', { name: '검색' }).fill('T000000000001');
  await expect(page.getByText('1–1 / 1건')).toBeVisible();
  await expect(page.getByText('T000000000001')).toBeVisible();
  await page.getByRole('combobox', { name: '페이지당' }).selectOption('10');
  await page.getByRole('button', { name: '초기화' }).click();
  await expect(page.getByText('1–10 / 31건')).toBeVisible();
  await expect(page.getByText('T000000000011')).toHaveCount(0);
});
