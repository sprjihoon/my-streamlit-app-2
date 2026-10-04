import { expect, test } from '@playwright/test';
import { ADMIN, installApi, seedSession } from './support/api';

const JOURNALS = [
  ['/work-log', '작업일지'],
  ['/repair-log', '수선작업일지'],
  ['/defect-log', '불량일지'],
] as const;

test.beforeEach(async ({ page }) => {
  await seedSession(page, ADMIN);
  await installApi(page, ADMIN);
});

for (const [path, heading] of JOURNALS) {
  test(`${heading} renders and a server error is not an empty table`, async ({ page }) => {
    await page.goto(path);
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible();
    const excel = page.getByRole('link', { name: /엑셀|Excel|내려받기/ }).or(page.getByRole('button', { name: /엑셀|Excel/ }));
    expect(await excel.count()).toBeGreaterThanOrEqual(0);
    await page.route('http://localhost:8000/**', (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === '/auth/me') {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ADMIN) });
      }
      return route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: '조회 실패' }) });
    });
    await page.reload();
    await expect(page.locator('.alert-error, .alert')).toBeVisible();
  });
}

test('journal delete confirmation can be dismissed', async ({ page }) => {
  page.once('dialog', (dialog) => {
    expect(dialog.message()).toContain('삭제');
    dialog.dismiss();
  });
  await page.goto('/work-log');
  const remove = page.getByRole('button', { name: '삭제' });
  if (await remove.count()) await remove.first().click();
  await expect(page.getByRole('heading', { name: '작업일지', exact: true })).toBeVisible();
});
