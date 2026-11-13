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
    if (url.pathname.endsWith('/export') || url.pathname.endsWith('/report')) {
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
  expect(registeredStart!.width).toBeLessThan(220);
  const statusBox = await page.getByLabel('상태').boundingBox();
  const sellerBox = await page.getByRole('textbox', { name: '판매처', exact: true }).boundingBox();
  expect(statusBox && sellerBox).toBeTruthy();
  expect(statusBox!.width).toBeLessThan(160);
  expect(sellerBox!.width).toBeGreaterThan(statusBox!.width);
  const seller = page.getByRole('textbox', { name: '판매처', exact: true });
  await expect(seller).toHaveJSProperty('tagName', 'INPUT');
  await seller.fill('봄');
  await page.getByRole('button', { name: '판매처 봄 추가', exact: true }).click();
  await expect(page.getByRole('button', { name: '판매처 봄 빼기', exact: true })).toBeVisible();
  await expect(seller).toHaveValue('');
  await seller.fill('봄');
  await page.getByRole('button', { name: '판매처 봄날 추가', exact: true }).click();
  await expect(page.getByRole('button', { name: '판매처 봄날 빼기', exact: true })).toBeVisible();
  await page.getByLabel('상품명').fill('셔');
  await page.getByRole('button', { name: '셔츠' }).click();
  await expect(page.getByLabel('상품명')).toHaveValue('셔츠');
  const supplier = page.getByRole('textbox', { name: '공급처', exact: true });
  await supplier.fill('헤이즐');
  await page.getByRole('button', { name: '공급처 헤이즐 추가', exact: true }).click();
  await supplier.fill('헤이즐');
  await page.getByRole('button', { name: '공급처 헤이즐샵 추가', exact: true }).click();
  await expect(page.getByRole('button', { name: '공급처 헤이즐 빼기', exact: true })).toBeVisible();
  await expect(page.getByLabel('CS이력')).toHaveCount(0);
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
  const reportDownload = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.endsWith('/return-info/report') && url.searchParams.get('q') === '모자';
  });
  await page.getByRole('button', { name: '보고서 다운로드' }).click();
  await reportDownload;
});

test('return info updates selected defect values and keeps a memo', async ({ page }) => {
  let posted: Record<string, unknown> | null = null;
  const rows: Array<{
    id: number;
    관리번호: string;
    상품명: string;
    불량: string;
    수정사항메모: string | null;
  }> = [
    { id: 11, 관리번호: '111', 상품명: '셔츠', 불량: '불량', 수정사항메모: null },
    { id: 22, 관리번호: '222', 상품명: '바지', 불량: '정상', 수정사항메모: null },
  ];
  await seedSession(page, STAFF);
  await installApi(page, STAFF);
  await page.route('http://localhost:8000/return-info**', async (route) => {
    const url = new URL(route.request().url());
    const request = route.request();
    if (request.method() === 'POST' && url.pathname.endsWith('/defect')) {
      posted = request.postDataJSON() as Record<string, unknown>;
      rows[0].불량 = '정상';
      rows[1].불량 = '정상';
      rows[0].수정사항메모 = '재검수';
      rows[1].수정사항메모 = '재검수';
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ updated: 2, 불량: '정상', 수정사항메모: '재검수' }),
      });
    }
    if (url.pathname.endsWith('/options')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ 판매처: [], 상품명: [], 공급처: [] }),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        columns: [...COLUMNS, '수정사항메모', '입력구분'],
        rows,
        total: rows.length,
        page: 1,
        page_size: 50,
      }),
    });
  });

  await page.goto('/return-info');
  await page.getByRole('checkbox', { name: '이 페이지 모두 선택' }).check();
  await page.getByLabel('변경할 불량').selectOption('불량');
  await page.getByLabel('수정사항메모 입력').fill('재검수');
  await page.getByRole('button', { name: '선택 2건 변경' }).click();
  await expect(page.getByRole('dialog')).toContainText('선택한 2건의 불량을 불량으로 바꿉니다.');
  await expect(page.getByRole('dialog')).toContainText('수정사항메모: 재검수');
  await page.getByRole('button', { name: '아니오' }).click();
  expect(posted).toBeNull();

  await page.getByLabel('변경할 불량').selectOption('정상');
  await page.getByRole('button', { name: '선택 2건 변경' }).click();
  await page.getByRole('button', { name: '네' }).click();
  await expect(page.getByText('2건의 불량을 정상으로 바꿨습니다.')).toBeVisible();
  expect(posted).toEqual({ ids: [11, 22], 불량: '정상', 수정사항메모: '재검수' });
  await expect(page.getByRole('columnheader', { name: '수정사항메모' })).toBeVisible();
  await expect(page.getByRole('cell', { name: '재검수' })).toHaveCount(2);
  await expect(page.getByRole('checkbox', { name: '이 페이지 모두 선택' })).not.toBeChecked();
});

test('return info manual entry opens a field for every header', async ({ page }) => {
  let posts = 0;
  let created: Record<string, unknown> | null = null;
  await seedSession(page, STAFF);
  await installApi(page, STAFF);
  await page.route('http://localhost:8000/return-info**', async (route) => {
    const url = new URL(route.request().url());
    const request = route.request();
    if (request.method() === 'POST' && (url.pathname === '/return-info' || url.pathname === '/return-info/')) {
      posts += 1;
      created = { ...(request.postDataJSON() as Record<string, unknown>), 입력구분: '수동 입력' };
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 9, row: created }),
      });
    }
    if (url.pathname.endsWith('/options')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ 판매처: [], 상품명: [], 공급처: [] }),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        columns: [...COLUMNS, '입력구분'],
        rows: created ? [created] : [],
        total: created ? 1 : 0,
        page: 1,
        page_size: 50,
      }),
    });
  });

  await page.goto('/return-info');
  await page.getByRole('button', { name: '직접 입력' }).click();
  const dialog = page.getByRole('dialog', { name: '반품정보 직접 입력' });
  await expect(dialog).toBeVisible();
  for (const column of COLUMNS) {
    await expect(dialog.locator('label', { hasText: column })).toBeVisible();
    await expect(dialog.getByLabel(`직접입력 ${column}`)).toBeVisible();
  }
  await dialog.getByRole('button', { name: '저장' }).click();
  await expect(dialog.getByText('등록일 외에 내용을 하나 이상 입력해 주세요.')).toBeVisible();
  expect(posts).toBe(0);

  await dialog.getByLabel('직접입력 등록일').fill('2026-11-05');
  await dialog.getByLabel('직접입력 관리번호').fill('M-1');
  await dialog.getByLabel('직접입력 상품명').fill('셔츠');
  await dialog.getByLabel('직접입력 수량').fill('2');
  const saved = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return request.method() === 'POST' && url.pathname === '/return-info';
  });
  await dialog.getByRole('button', { name: '저장' }).click();
  const request = await saved;
  const body = request.postDataJSON();
  expect(body.등록일).toBe('2026-11-05');
  expect(body.등록자).toBe('물류담당');
  expect(body.관리번호).toBe('M-1');
  expect(body.상품명).toBe('셔츠');
  expect(body.수량).toBe(2);
  expect(body.CS이력).toBeNull();
  await expect(page.getByText('목록에 수동 입력으로 표시됩니다.')).toBeVisible();
  await expect(page.getByRole('columnheader', { name: '입력구분' })).toBeVisible();
  await expect(page.getByRole('cell', { name: '수동 입력' })).toBeVisible();
  await expect(dialog).toHaveCount(0);
  expect(posts).toBe(1);

  await page.getByRole('button', { name: '직접 입력' }).click();
  await page.getByRole('dialog', { name: '반품정보 직접 입력' }).getByRole('button', { name: '취소' }).click();
  await expect(page.getByRole('dialog', { name: '반품정보 직접 입력' })).toHaveCount(0);
  await expect(page.getByLabel('직접입력 상태')).toHaveCount(0);
  expect(posts).toBe(1);
});

test('return info log shows the actor and restores a deleted row', async ({ page }) => {
  let restored = 0;
  await seedSession(page, STAFF);
  await installApi(page, STAFF);
  await page.route('http://localhost:8000/return-info/logs**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === 'POST' && url.pathname.endsWith('/restore')) {
      restored += 1;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 4, return_info_id: 11, restored: true }),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        rows: [{
          id: 4,
          return_info_id: 11,
          action: 'delete',
          action_label: '삭제',
          actor_name: '물류담당',
          summary: '삭제 · 셔츠 · 111',
          changes: [],
          created_at: '2026-11-13 18:20:00',
          can_restore: restored === 0,
        }],
        total: 1,
        page: 1,
        page_size: 50,
        summary: { create: 0, update: 1, delete: 1, restore: restored },
      }),
    });
  });

  await page.goto('/return-info-log');
  await expect(page.getByRole('heading', { name: '반품정보 조회 로그 분석' })).toBeVisible();
  await expect(page.getByRole('cell', { name: '물류담당' })).toBeVisible();
  await expect(page.getByRole('cell', { name: '삭제 · 셔츠 · 111' })).toBeVisible();
  await page.getByRole('button', { name: '삭제 · 셔츠 · 111 되돌리기' }).click();
  await page.getByRole('button', { name: '네' }).click();
  await expect(page.getByText('삭제한 반품정보를 목록으로 되돌렸습니다.')).toBeVisible();
  expect(restored).toBe(1);
  await expect(page.getByRole('button', { name: '삭제 · 셔츠 · 111 되돌리기' })).toHaveCount(0);
});
