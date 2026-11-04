import { expect, test } from '@playwright/test';
import { ADMIN, installApi, seedSession, STAFF } from './support/api';

const COLUMNS = [
  '상태', '등록일', '등록자', '입고일', '관리번호', '발주일', '판매처',
  '주문번호', '수령자', '상품명', '옵션', '수량', '불량', 'CS이력', '반품메모',
];

test('return info menu sits below marketing outside a category', async ({ page }) => {
  await seedSession(page, ADMIN);
  await installApi(page, ADMIN);
  await page.goto('/');
  const link = page.locator('aside.sidebar nav > a', { hasText: '반품정보 조회' });
  await expect(link).toBeVisible();
  await expect(page.locator('.sidebar-group a', { hasText: '반품정보 조회' })).toHaveCount(0);
  const marketing = await page.getByRole('button', { name: '마케팅' }).boundingBox();
  const item = await link.boundingBox();
  const billing = await page.getByRole('button', { name: '실 청구서' }).boundingBox();
  expect(marketing).not.toBeNull();
  expect(item).not.toBeNull();
  expect(billing).not.toBeNull();
  expect(item!.y).toBeGreaterThan(marketing!.y);
  expect(item!.y).toBeLessThan(billing!.y);
});

test('staff can open the return info menu', async ({ page }) => {
  await seedSession(page, STAFF);
  await installApi(page, STAFF);
  await page.goto('/insights');
  await page.getByRole('link', { name: '반품정보 조회' }).click();
  await expect(page.getByRole('heading', { name: '반품정보 조회' })).toBeVisible();
});

test('return info page filters every header and pages the rows', async ({ page }) => {
  await seedSession(page, ADMIN);
  await installApi(page, ADMIN);
  await page.route('http://localhost:8000/return-info**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/export')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        body: Buffer.from('xlsx'),
      });
    }
    const pageNo = Number(url.searchParams.get('page') || '1');
    const pageSize = Number(url.searchParams.get('page_size') || '50');
    const row = pageNo === 1
      ? { 관리번호: '111', 반품메모: '아무개 입고', 상태: '입고완료' }
      : { 관리번호: '333', 반품메모: '아무개 입고', 상태: '입고완료' };
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        columns: COLUMNS,
        rows: [row],
        total: pageSize * 2,
        page: pageNo,
        page_size: pageSize,
      }),
    });
  });

  await page.goto('/return-info');
  await expect(page.getByRole('heading', { name: '반품정보 조회' })).toBeVisible();
  for (const column of COLUMNS) {
    await expect(page.getByText(column, { exact: true }).first()).toBeVisible();
  }
  const registeredStart = await page.getByLabel('등록일 시작').boundingBox();
  const registeredEnd = await page.getByLabel('등록일 종료').boundingBox();
  const inboundStart = await page.getByLabel('입고일 시작').boundingBox();
  expect(registeredStart && registeredEnd && inboundStart).toBeTruthy();
  expect(registeredEnd!.y).toBeGreaterThanOrEqual(registeredStart!.y + registeredStart!.height - 1);
  expect(inboundStart!.x).toBeGreaterThanOrEqual(registeredStart!.x + registeredStart!.width - 1);
  await expect(page.getByRole('cell', { name: '111' })).toBeVisible();
  await page.getByRole('button', { name: '다음' }).click();
  await expect(page.getByRole('cell', { name: '333' })).toBeVisible();
  await expect(page.getByText('2 / 2')).toBeVisible();
});
