import { expect, test } from '@playwright/test';
import { ADMIN, installApi, seedSession, STAFF } from './support/api';

test.beforeEach(async ({ page }) => {
  await seedSession(page, ADMIN);
  await installApi(page, ADMIN);
});

test('sidebar accordion opens a menu route', async ({ page }) => {
  await page.goto('/');
  const inboundAboveReturns = await page.locator('aside.sidebar nav').evaluate((nav) => {
    const inbound = [...nav.querySelectorAll('.sidebar-group')].find((group) =>
      group.querySelector('button')?.textContent?.includes('입고'),
    );
    const returns = [...nav.querySelectorAll('a')].find((link) => link.textContent?.includes('반품정보 조회'));
    if (!inbound || !returns) return false;
    return Boolean(inbound.compareDocumentPosition(returns) & Node.DOCUMENT_POSITION_FOLLOWING)
      && inbound.nextElementSibling === returns;
  });
  expect(inboundAboveReturns).toBe(true);
  await page.getByRole('button', { name: '일지' }).click();
  await page.getByRole('link', { name: '작업일지', exact: true }).click();
  await expect(page).toHaveURL(/\/work-log$/);
  await expect(page.getByRole('heading', { name: '작업일지' })).toBeVisible();
  await expect(page.locator('a.active', { hasText: '작업일지' })).toBeVisible();
  const journal = page.locator('.sidebar-group', { has: page.getByRole('button', { name: '일지', exact: true }) });
  await expect(journal.getByRole('link', { name: '입고일지', exact: true })).toHaveCount(0);
  await expect(journal.getByRole('link', { name: '통합현황', exact: true })).toHaveCount(0);

  await page.getByRole('button', { name: '입고', exact: true }).click();
  await page.getByRole('link', { name: '입고일지', exact: true }).click();
  await expect(page).toHaveURL(/\/inbound-log$/);
  await expect(page.getByRole('heading', { name: '입고일지' })).toBeVisible();
  await page.getByRole('link', { name: '통합현황', exact: true }).click();
  await expect(page).toHaveURL(/\/inbound-overview$/);
  await expect(page.getByRole('heading', { name: '통합 현황', exact: true })).toBeVisible();
});

test('public, share, print, and mobile work pages have no sidebar', async ({ page }) => {
  await page.goto('/estimate');
  await expect(page.getByRole('heading', { name: '스프링풀필먼트 견적확인하기' })).toBeVisible();
  await expect(page.locator('aside.sidebar')).toHaveCount(0);

  await page.goto('/share/demo-token');
  await expect(page.getByText('스프링')).toBeVisible();
  await expect(page.locator('aside.sidebar')).toHaveCount(0);

  await page.goto('/overseas-print/9', { waitUntil: 'commit' });
  await expect(page.locator('aside.sidebar')).toHaveCount(0);

  await page.goto('/inbound/1');
  await expect(page.locator('aside.sidebar')).toHaveCount(0);
});

test('staff still reaches operational menus', async ({ page }) => {
  await seedSession(page, STAFF);
  await installApi(page, STAFF);
  await page.goto('/insights');
  await page.getByRole('button', { name: '국내출고' }).click();
  await page.getByRole('link', { name: '출고 접수' }).click();
  await expect(page.getByRole('heading', { name: '국내 출고' })).toBeVisible();
});

const PAGES: Array<[string, string]> = [
  ['/work-log', '작업일지'],
  ['/repair-log', '수선작업일지'],
  ['/defect-log', '불량일지'],
  ['/inbound-log', '입고일지'],
  ['/inbound-overview', '통합 현황'],
  ['/return-request', '회수신청'],
  ['/kpost-pickup-list', '회수신청 목록'],
  ['/saved-recipients', '저장된 주소지'],
  ['/domestic-shipping', '국내 출고'],
  ['/domestic-shipping-list', '출고 목록'],
  ['/domestic-saved-recipients', '출고 주소지'],
  ['/overseas-shipping', '해외배송 접수'],
  ['/overseas-shipping-list', '해외배송 접수목록'],
  ['/invoice', '인보이스 계산'],
  ['/invoice-list', '인보이스 목록'],
  ['/estimate-list', '견적서 목록'],
  ['/leave', '연월차 관리'],
  ['/leave/calendar', '연차 달력'],
  ['/rates', '글로벌 요금표 관리'],
  ['/storage', '보관료 관리'],
  ['/settings', '회사 설정'],
];

test('main menus render their headings', async ({ page }) => {
  test.setTimeout(180_000);
  for (const [path, heading] of PAGES) {
    await page.goto(path);
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible();
  }
});
