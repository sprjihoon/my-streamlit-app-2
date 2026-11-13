import { expect, test, type Page } from '@playwright/test';
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

test('staff can upload return info but cannot delete it', async ({ page }) => {
  await seedSession(page, STAFF);
  await installApi(page, STAFF);
  await page.goto('/return-info');
  await expect(page.getByRole('heading', { name: '반품정보 조회' })).toBeVisible();
  const upload = page.locator('details.return-filter-accordion', { hasText: '반품정보 업로드' });
  await expect(upload).toBeVisible();
  await upload.locator('summary').click();
  await expect(page.getByLabel('반품정보 엑셀')).toBeAttached();
  await expect(page.getByRole('button', { name: '데이터 초기화' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '기간 데이터 삭제' })).toHaveCount(0);
  await expect(page.getByLabel('반품정보 삭제 시작일')).toHaveCount(0);
});

test('stale admin flag does not show return info reset', async ({ page }) => {
  await seedSession(page, STAFF);
  await page.addInitScript(() => {
    localStorage.setItem('isAdmin', 'true');
  });
  await installApi(page, STAFF);
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
  await page.goto('/return-info');
  await expect(page.getByRole('heading', { name: '반품정보 조회' })).toBeVisible();
  const upload = page.locator('details.return-filter-accordion', { hasText: '반품정보 업로드' });
  await expect(upload).toBeVisible();
  await upload.locator('summary').click();
  await expect(page.getByLabel('반품정보 엑셀')).toBeAttached();
  await expect(page.getByRole('button', { name: '데이터 초기화' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '기간 데이터 삭제' })).toHaveCount(0);
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

async function openReturnUpload(page: Page) {
  await page.goto('/return-info');
  const upload = page.locator('details.return-filter-accordion', { hasText: '반품정보 업로드' });
  await upload.locator('summary').click();
  await expect(page.getByText('재입고 대기 엑셀입니다.')).toBeVisible();
  return upload;
}

test('dragging an excel onto return info upload sends that file', async ({ page }) => {
  await seedSession(page, STAFF);
  await installApi(page, STAFF);
  await page.route('http://localhost:8000/upload', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, message: '반품정보 업로드 완료' }),
    });
  });

  await openReturnUpload(page);
  const uploaded = page.waitForRequest((request) => (
    request.method() === 'POST' && new URL(request.url()).pathname === '/upload'
  ));
  await page.locator('.return-upload-body .file-upload').evaluate((el) => {
    const transfer = new DataTransfer();
    transfer.items.add(new File(['excel'], 'return-waiting.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }));
    const drop = new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: transfer });
    el.dispatchEvent(drop);
  });
  const request = await uploaded;
  expect(request.postData() || '').toContain('return-waiting.xlsx');
  await expect(page.getByText('반품정보 업로드 완료')).toBeVisible();
});

test('pasted excel uploads and other files stay out', async ({ page }) => {
  await seedSession(page, STAFF);
  await installApi(page, STAFF);
  let uploads = 0;
  await page.route('http://localhost:8000/upload', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    uploads += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, message: '붙여넣은 반품정보 업로드 완료' }),
    });
  });

  await openReturnUpload(page);
  await page.evaluate(() => {
    const transfer = new DataTransfer();
    transfer.items.add(new File(['notes'], '메모.txt', { type: 'text/plain' }));
    const event = new Event('paste', { bubbles: true, cancelable: true });
    Object.defineProperty(event, 'clipboardData', { value: transfer });
    window.dispatchEvent(event);
  });
  await expect(page.getByText('엑셀 파일(.xlsx, .xls)만 업로드 가능합니다.')).toBeVisible();
  expect(uploads).toBe(0);

  const uploaded = page.waitForRequest((request) => (
    request.method() === 'POST' && new URL(request.url()).pathname === '/upload'
  ));
  await page.evaluate(() => {
    const transfer = new DataTransfer();
    transfer.items.add(new File(['excel'], 'pasted.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }));
    const event = new Event('paste', { bubbles: true, cancelable: true });
    Object.defineProperty(event, 'clipboardData', { value: transfer });
    window.dispatchEvent(event);
  });
  const request = await uploaded;
  expect(request.postData() || '').toContain('pasted.xlsx');
  await expect(page.getByText('붙여넣은 반품정보 업로드 완료')).toBeVisible();
});
