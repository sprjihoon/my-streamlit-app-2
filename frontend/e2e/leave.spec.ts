import { expect, test } from '@playwright/test';
import { ADMIN, countCalls, installApi, seedSession, STAFF } from './support/api';

test('leave summary, calendar, and holiday screen render', async ({ page }) => {
  await seedSession(page, STAFF);
  await installApi(page, STAFF);
  await page.goto('/leave');
  await expect(page.getByRole('heading', { name: '연월차 관리' })).toBeVisible();
  await page.goto('/leave/calendar');
  await expect(page.getByRole('heading', { name: '연차 달력' })).toBeVisible();
});

test('leave without approvers records the selected date immediately', async ({ page }) => {
  await seedSession(page, STAFF);
  const calls = await installApi(page, STAFF);
  await page.goto('/leave');
  await page.getByRole('button', { name: '연차 신청' }).click();
  await expect(page.getByText('결재자 없음. 신청하면 선택한 날짜가 바로 반영됩니다.')).toBeVisible();
  await page.locator('input[type="date"]').nth(0).fill('2026-10-21');
  await page.locator('input[type="date"]').nth(1).fill('2026-10-21');
  await page.getByRole('button', { name: '바로 반영' }).click();
  await expect(page.getByText('날짜가 바로 반영되었습니다. 1일 (7시간)')).toBeVisible();
  const posted = calls.find((call) => call.method === 'POST' && call.path === '/leave/requests');
  expect(posted?.body).toContain('"start_date":"2026-10-21"');
  expect(posted?.body).toContain('"end_date":"2026-10-21"');
});

test('leave request and cancel stay on the local API', async ({ page }) => {
  await seedSession(page, STAFF);
  const calls = await installApi(page, STAFF);
  await page.goto('/leave');
  const apply = page.getByRole('button', { name: /신청/ });
  if (await apply.count()) await apply.first().click();
  page.once('dialog', (dialog) => dialog.dismiss());
  const cancel = page.getByRole('button', { name: '취소' });
  if (await cancel.count()) await cancel.first().click();
  expect(calls.filter((call) => call.path.includes('/cancel') && call.method !== 'GET')).toHaveLength(0);
});

test('admin confirms a pending leave from the calendar cell', async ({ page }) => {
  await seedSession(page, ADMIN);
  await installApi(page, ADMIN);
  await page.route('http://localhost:8000/leave/calendar**', async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, message: '연차 신청을 확정했습니다.', status: 'approved' }),
      });
      return;
    }
    const year = url.searchParams.get('year');
    const month = String(url.searchParams.get('month') || '1').padStart(2, '0');
    const day = `${year}-${month}-15`;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        year: Number(year),
        month: Number(month),
        is_admin: true,
        holidays: {},
        days: {
          [day]: [{
            request_id: 42,
            nickname: '직원',
            department: '패션팀',
            position: '',
            leave_type: '연차',
            hours: 7,
            status: 'pending',
          }],
        },
      }),
    });
  });

  await page.goto('/leave/calendar');
  await page.getByRole('button', { name: '직원 확정' }).click();
  await expect(page.getByText('연차 신청을 확정했습니다.')).toBeVisible();
});

test('admin leave screen is available to an admin', async ({ page }) => {
  await seedSession(page, ADMIN);
  await installApi(page, ADMIN);
  await page.goto('/leave');
  await expect(page.getByRole('heading', { name: '연월차 관리' })).toBeVisible();
  await expect(page.getByText(/승인|반려|관리/).first()).toBeVisible();
});
