import { expect, test } from '@playwright/test';
import { ADMIN, installApi, seedSession, STAFF } from './support/api';

test('return info upload card lives on the query page', async ({ page }) => {
  await seedSession(page, ADMIN);
  await installApi(page, ADMIN);
  await page.goto('/upload');
  await expect(page.getByRole('heading', { name: '원본 데이터 업로드' })).toBeVisible();

  const titles = page.locator('.grid-5 .card-header span');
  await expect(titles).toHaveText([
    '입고전표',
    '배송통계',
    '우체국접수',
    '우체국반품',
    '작업일지',
  ]);
  await expect(page.locator('select option').filter({ hasText: '반품정보' })).toHaveCount(0);
  await expect(page.getByText('재입고 대기 엑셀입니다.')).toHaveCount(0);

  await page.goto('/return-info');
  const upload = page.locator('details.return-filter-accordion', { hasText: '반품정보 업로드' });
  await expect(upload).toBeVisible();
  await expect(upload).not.toHaveAttribute('open', '');
  await expect(page.getByText('재입고 대기 엑셀입니다.')).toBeHidden();
  await upload.locator('summary').click();
  await expect(page.getByText('재입고 대기 엑셀입니다.')).toBeVisible();
  await expect(page.getByLabel('반품정보 엑셀')).toBeAttached();
});

test('staff cannot see the return info upload card', async ({ page }) => {
  await seedSession(page, STAFF);
  await installApi(page, STAFF);
  await page.goto('/return-info');
  await expect(page.getByRole('heading', { name: '반품정보 조회' })).toBeVisible();
  await expect(page.getByText('반품정보 업로드', { exact: true })).toHaveCount(0);
});
