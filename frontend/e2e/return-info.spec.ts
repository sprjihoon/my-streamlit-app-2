import { expect, test } from '@playwright/test';
import { ADMIN, installApi, seedSession, STAFF } from './support/api';

const COLUMNS = [
  '상태', '등록일', '등록자', '입고일', '관리번호', '발주일', '판매처',
  '주문번호', '수령자', '상품명', '바코드', '옵션', '수량', '불량', 'CS이력', '반품메모', '공급처',
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
    if (url.pathname.endsWith('/options')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ 판매처: ['봄', '봄날', '가을'], 상품명: ['셔츠', '바지'], 공급처: ['헤이즐', '헤이즐샵'] }),
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
  const accordions = page.locator('details.return-filter-accordion');
  await expect(accordions).toHaveCount(3);
  await expect(accordions.nth(0)).not.toHaveAttribute('open', '');
  await expect(accordions.nth(1)).not.toHaveAttribute('open', '');
  await expect(accordions.nth(2)).not.toHaveAttribute('open', '');
  await page.locator('summary', { hasText: '날짜' }).click();
  await page.locator('summary', { hasText: '조건' }).click();
  for (const column of COLUMNS) {
    await expect(page.getByText(column, { exact: true }).first()).toBeVisible();
  }
  const registeredStart = await page.getByLabel('등록일 시작').boundingBox();
  const registeredEnd = await page.getByLabel('등록일 종료').boundingBox();
  const inboundStart = await page.getByLabel('입고일 시작').boundingBox();
  expect(registeredStart && registeredEnd && inboundStart).toBeTruthy();
  expect(registeredEnd!.y).toBeGreaterThanOrEqual(registeredStart!.y + registeredStart!.height - 1);
  expect(inboundStart!.x).toBeGreaterThanOrEqual(registeredStart!.x + registeredStart!.width - 1);
  await expect(page.getByLabel('판매처')).toHaveJSProperty('tagName', 'INPUT');
  await expect(page.getByLabel('판매처 비슷한 값')).toHaveCount(0);
  await page.getByLabel('판매처').fill('봄');
  await expect(page.getByLabel('판매처 비슷한 값').locator('option')).toHaveText(['비슷한 값 선택', '봄', '봄날']);
  await page.getByLabel('판매처 비슷한 값').selectOption('봄날');
  await expect(page.getByLabel('판매처')).toHaveValue('봄날');
  await expect(page.getByLabel('판매처 비슷한 값')).toHaveCount(0);
  await page.getByLabel('상품명').fill('셔');
  await page.getByRole('button', { name: '셔츠' }).click();
  await expect(page.getByLabel('상품명')).toHaveValue('셔츠');
  await page.getByLabel('공급처').fill('헤이즐');
  await expect(page.getByLabel('공급처 비슷한 값').locator('option')).toHaveText(['비슷한 값 선택', '헤이즐', '헤이즐샵']);
  await expect(page.getByLabel('CS이력')).toHaveJSProperty('tagName', 'TEXTAREA');
  const keywordSearch = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.endsWith('/return-info') && url.searchParams.get('q') === '모자';
  });
  await page.getByLabel('전체 검색').fill('모자');
  await page.getByRole('button', { name: '검색' }).click();
  await keywordSearch;
  await expect(page.getByRole('cell', { name: '111' })).toBeVisible();
  await page.getByRole('button', { name: '다음' }).click();
  await expect(page.getByRole('cell', { name: '333' })).toBeVisible();
  await expect(page.getByText('2 / 2')).toBeVisible();
});
