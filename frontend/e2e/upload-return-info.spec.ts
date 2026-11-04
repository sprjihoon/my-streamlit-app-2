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
  await expect(page.getByRole('button', { name: '데이터 초기화' })).toHaveCount(0);
});

test('admin must confirm before resetting return info', async ({ page }) => {
  await seedSession(page, ADMIN);
  await installApi(page, ADMIN);
  await page.route('http://localhost:8000/upload/list**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        uploads: [{
          id: 9,
          filename: 'r.xlsx',
          원본명: '반품.xlsx',
          table_name: 'return_info',
          시작일: '2026-11-01',
          종료일: '2026-11-04',
          업로드시각: '2026-11-04 09:00',
        }],
      }),
    });
  });
  await page.route('http://localhost:8000/upload/table/return_info**', async (route) => {
    if (route.request().method() !== 'DELETE') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, message: '반품정보 테이블 초기화 완료' }),
    });
  });

  await page.goto('/return-info');
  await page.locator('details.return-filter-accordion', { hasText: '반품정보 업로드' }).locator('summary').click();
  await page.getByRole('button', { name: '데이터 초기화' }).click();
  const dialog = page.getByRole('alertdialog', { name: '데이터 초기화 확인' });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('되돌릴 수 없습니다');

  await dialog.getByRole('button', { name: '취소' }).click();
  await expect(dialog).toHaveCount(0);

  await page.getByRole('button', { name: '데이터 초기화' }).click();
  const deleted = page.waitForRequest((request) => (
    request.method() === 'DELETE' && request.url().includes('/upload/table/return_info')
  ));
  await page.getByRole('alertdialog', { name: '데이터 초기화 확인' }).getByRole('button', { name: '삭제 확인' }).click();
  await deleted;
  await expect(page.getByText('반품정보 테이블 초기화 완료')).toBeVisible();
});
