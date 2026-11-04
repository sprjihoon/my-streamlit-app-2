import { expect, test } from '@playwright/test';
import { ADMIN, installApi, seedSession } from './support/api';

test.beforeEach(async ({ page }) => {
  await seedSession(page, ADMIN);
  await installApi(page, ADMIN);
});

test('return info upload card sits beside the work log card', async ({ page }) => {
  await page.goto('/upload');
  await expect(page.getByRole('heading', { name: '원본 데이터 업로드' })).toBeVisible();

  const titles = page.locator('.grid-6 .card-header span');
  await expect(titles).toHaveText([
    '입고전표',
    '배송통계',
    '우체국접수',
    '우체국반품',
    '작업일지',
    '반품정보',
  ]);

  const workLog = titles.filter({ hasText: /^작업일지$/ });
  const returnInfo = titles.filter({ hasText: /^반품정보$/ });
  const workBox = await workLog.boundingBox();
  const returnBox = await returnInfo.boundingBox();
  expect(workBox).not.toBeNull();
  expect(returnBox).not.toBeNull();
  expect(returnBox!.x).toBeGreaterThan(workBox!.x + workBox!.width - 8);
  expect(Math.abs(returnBox!.y - workBox!.y)).toBeLessThan(12);

  const periodOptions = page.locator('select option');
  await expect(periodOptions.filter({ hasText: '반품정보' })).toHaveCount(0);
  await expect(page.getByText('엑셀 열은 그대로 저장됩니다.')).toBeVisible();
  await expect(page.getByRole('cell', { name: '작업일지' })).toBeVisible();
});
