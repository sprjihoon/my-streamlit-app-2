import { expect, test } from '@playwright/test';
import { ADMIN, countCalls, installApi, seedSession, STAFF } from './support/api';

test('saved address fills the pickup form and validation blocks an empty submit', async ({ page }) => {
  await seedSession(page, STAFF);
  const calls = await installApi(page, STAFF);
  await page.goto('/return-request');
  await expect(page.getByRole('heading', { name: '회수신청' })).toBeVisible();
  await page.getByLabel('저장된 주소지 별칭').selectOption('3');
  await expect(page.getByLabel('수취인 이름')).toHaveValue('홍길동');
  await expect(page.getByLabel('우편번호')).toHaveAttribute('readonly', '');
  await page.getByRole('checkbox', { name: '해당 정보 저장하기' }).check();
  await page.getByRole('button', { name: '테스트 접수' }).click();
  await expect(page.getByText('주소지를 저장하려면 별칭을 입력해주세요.')).toBeVisible();
  expect(countCalls(calls, 'POST', '/kpost-pickup')).toBe(0);
});

test('address search failure does not call the post office', async ({ page }) => {
  await seedSession(page, STAFF);
  const calls = await installApi(page, STAFF);
  await page.goto('/return-request');
  await page.getByRole('button', { name: '주소 검색' }).click();
  await expect(page.getByText('주소 검색을 불러오지 못했습니다.')).toBeVisible();
  expect(calls.some((call) => call.path.includes('epost'))).toBe(false);
});

test('successful and failed pickup keep the request contract', async ({ page }) => {
  await seedSession(page, STAFF);
  const calls = await installApi(page, STAFF);
  await page.goto('/return-request');
  await page.getByLabel('저장된 주소지 별칭').selectOption('3');
  await page.getByLabel('상세주소 (동·호·층)').fill('101호');
  await page.route('http://localhost:8000/kpost-pickup**', async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === 'POST' && url.pathname === '/kpost-pickup') {
      return route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ detail: '우체국 접수 실패' }) });
    }
    return route.fallback();
  });
  await page.getByRole('button', { name: '테스트 접수' }).click();
  await expect(page.getByText('우체국 접수 실패')).toBeVisible();
  await expect(page.getByLabel('수취인 이름')).toHaveValue('홍길동');

  await page.unroute('http://localhost:8000/kpost-pickup**');
  await page.getByRole('button', { name: '테스트 접수' }).click();
  await expect(page.getByText('9876543210987')).toBeVisible();
  const create = calls.find((call) => call.method === 'POST' && call.path === '/kpost-pickup');
  expect(create?.body || '').toContain('"recipient_name":"홍길동"');
  expect(create?.body || '').not.toContain('epost.go.kr');
});

test('list status, query return, and cancel confirmation sends nothing', async ({ page }) => {
  await seedSession(page, STAFF);
  const calls = await installApi(page, STAFF);
  page.on('dialog', (dialog) => dialog.dismiss());
  await page.goto('/kpost-pickup-list?treat_status=requested');
  await expect(page.getByRole('table').getByText('신청접수')).toBeVisible();
  await page.getByRole('button', { name: '취소', exact: true }).click();
  expect(calls.filter((call) => call.path.includes('/cancel'))).toHaveLength(0);
  await expect(page).toHaveURL(/treat_status=requested/);
});

test('admin can see manual status editing and staff cannot', async ({ page }) => {
  await seedSession(page, STAFF);
  await installApi(page, STAFF);
  await page.goto('/kpost-pickup-list');
  await expect(page.getByTitle('관리자: 상태 수동 수정')).toHaveCount(0);

  await page.evaluate(() => localStorage.clear());
  await seedSession(page, ADMIN);
  await installApi(page, ADMIN);
  await page.goto('/kpost-pickup-list');
  await expect(page.getByTitle('관리자: 상태 수동 수정')).toBeVisible();
});
