import type { Page, Request, Route } from '@playwright/test';

export type SessionUser = {
  user_id: number;
  username: string;
  nickname: string;
  is_admin: boolean;
  department: string;
};

export const ADMIN: SessionUser = {
  user_id: 1,
  username: 'admin',
  nickname: '관리자',
  is_admin: true,
  department: '관리',
};

export const STAFF: SessionUser = {
  user_id: 2,
  username: 'staff',
  nickname: '물류담당',
  is_admin: false,
  department: '물류팀',
};

export type ApiCall = { method: string; path: string; body: string | null; search?: string };

const PARTY = {
  name: '스프링',
  phone: '01012345678',
  zip: '41940',
  addr1: '대구 중구 중앙대로 394',
  addr2: '3층',
};

const DOMESTIC_ITEM = {
  id: 7,
  vendor_id: 1,
  vendor_name: '스프링',
  office_ser: '260537802',
  api_sender_name: '스프링',
  api_sender_phone: '01012345678',
  api_sender_zip: '41940',
  api_sender_addr1: '대구 중구 중앙대로 394',
  api_sender_addr2: '1층',
  print_sender_name: '보내는사람',
  print_sender_phone: '01011112222',
  print_sender_zip: '41940',
  print_sender_addr1: '대구 중구 중앙대로 394',
  print_sender_addr2: '2층',
  recipient_name: '홍길동',
  recipient_phone: '01012345678',
  recipient_zip: '06236',
  recipient_addr1: '서울 강남구 테헤란로 1',
  recipient_addr2: '101호',
  goods_name: '의류',
  goods_qty: 1,
  box_size: 'SMALL',
  weight: 2,
  volume: 80,
  notes: '',
  order_no: 'D-100',
  tracking_no: '1234567890123',
  price: '3500',
  post_office: '서울중앙',
  status: 'requested',
  is_test: true,
  created_by: '물류담당',
  created_at: '2026-10-04T09:00:00',
};

const KPOST_ITEM = {
  id: 4,
  order_no: 'K-100',
  recipient_name: '홍길동',
  recipient_phone: '01012345678',
  zipcode: '06236',
  addr1: '서울 강남구 테헤란로 1',
  addr2: '101호',
  pickup_date: '2026-10-06',
  goods_name: '의류',
  box_size: 'MICRO',
  box_quantity: 1,
  notes: '',
  tracking_no: '9876543210987',
  treat_status: '신청접수',
  treat_status_name: '신청접수',
  status: 'requested',
  is_test: true,
  created_by: '물류담당',
  created_at: '2026-10-04T09:00:00',
};

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

export async function seedSession(page: Page, user: SessionUser, mustChange = false) {
  await page.addInitScript(
    ({ user, mustChange }) => {
      localStorage.setItem('token', 'test-token');
      localStorage.setItem('user', JSON.stringify(user));
      localStorage.setItem('isAdmin', user.is_admin ? 'true' : 'false');
      if (mustChange) localStorage.setItem('must_change_password', 'true');
      else localStorage.removeItem('must_change_password');
    },
    { user, mustChange },
  );
}

export async function installApi(page: Page, user: SessionUser) {
  const calls: ApiCall[] = [];
  const record = (request: Request) => {
    const url = new URL(request.url());
    calls.push({ method: request.method(), path: url.pathname, body: request.postData(), search: url.search });
  };

  await page.route('https://t1.daumcdn.net/**', (route) => route.abort());
  await page.route('**://maps.googleapis.com/**', (route) => route.abort());
  await page.route('**://*.epost.go.kr/**', (route) => route.abort());
  await page.route('**://*.fedex.com/**', (route) => route.abort());

  await page.route('http://localhost:8000/**', async (route) => {
    const request = route.request();
    record(request);
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === '/auth/login' && method === 'POST') {
      const body = request.postDataJSON() as { password?: string };
      if (body.password === 'wrong') {
        return json(route, { detail: '아이디 또는 비밀번호가 올바르지 않습니다.' }, 401);
      }
      return json(route, { token: 'test-token', user, must_change_password: false });
    }
    if (path === '/auth/me') return json(route, user);
    if (path === '/auth/logout') return json(route, { success: true });
    if (path === '/auth/change-password') return json(route, { success: true });
    if (path === '/auth/users/me/can-manage') {
      return json(route, { can_manage: user.is_admin, department: user.department, position: user.is_admin ? '관리자' : '사원' });
    }
    if (path === '/auth/users') return json(route, []);
    if (path === '/health') return json(route, { status: 'ok', version: 'test' });
    if (path === '/upload/list') {
      return json(route, {
        success: true,
        uploads: [{ id: 1, filename: 'a.xlsx', 원본명: '입고.xlsx', table_name: 'work_log', 시작일: '', 종료일: '', 업로드시각: '2026-10-04 09:00' }],
      });
    }
    if (path === '/domestic-shipping/meta') {
      return json(route, {
        live_ready: false,
        box_sizes: [
          { code: 'MICRO', label: '극소', desc: '1kg · 45cm', weight: 1, volume: 45 },
          { code: 'SMALL', label: '소형', desc: '소', weight: 2, volume: 80 },
        ],
      });
    }
    if (path === '/domestic-shipping/saved-recipients' && method === 'GET') {
      return json(route, {
        items: [{
          id: 3, label: '출고본사', recipient_name: '홍길동', recipient_phone: '01012345678',
          zipcode: '06236', addr1: '서울 강남구 테헤란로 1', addr2: '101호', created_at: '2026-10-01',
        }],
      });
    }
    if (path === '/domestic-shipping/vendors' && method === 'GET') {
      return json(route, {
        items: [{
          id: 1, name: '스프링', office_ser: '260537802', sender_name: '스프링',
          sender_phone: '01012345678', sender_zip: '41940', sender_addr1: '대구 중구 중앙대로 394', sender_addr2: '1층',
        }],
      });
    }
    if (path === '/domestic-shipping/preview' && method === 'POST') {
      return json(route, {
        ok: true,
        live_ready: false,
        preview: {
          vendor_name: '스프링',
          office_ser: '260537802',
          api_sender: PARTY,
          print_sender: { ...PARTY, name: '보내는사람' },
          recipient: { ...PARTY, name: '홍길동' },
          goods_name: '의류',
          goods_qty: 1,
          label_count: 1,
          box_size: 'SMALL',
          box_label: '소형',
          weight: 2,
          volume: 80,
        },
      });
    }
    if (path === '/domestic-shipping' && method === 'POST') {
      return json(route, { success: true, id: 7, order_no: 'D-100', tracking_no: '1234567890123', tracking_nos: ['1234567890123'], is_test: true });
    }
    if (path === '/domestic-shipping' && method === 'GET') return json(route, { items: [DOMESTIC_ITEM] });
    if (path === '/domestic-shipping/7' && method === 'GET') return json(route, DOMESTIC_ITEM);
    if (path === '/kpost-pickup/meta') {
      return json(route, {
        vendor: 'spring',
        default_pickup_date: '2026-10-06',
        max_pickup_date: '2026-10-27',
        today: '2026-10-04',
        box_sizes: [{ code: 'MICRO', label: '초소형', desc: '초소형', weight: 1, volume: 40 }],
        live_ready: false,
        office_ser: '260537802',
        center: { name: '스프링풀필먼트', addr: '대구 중구 중앙대로 394' },
      });
    }
    if (path === '/kpost-pickup/saved-recipients' && method === 'GET') {
      return json(route, {
        items: [{
          id: 3, label: '본사', recipient_name: '홍길동', recipient_phone: '01012345678',
          zipcode: '06236', addr1: '서울 강남구 테헤란로 1', addr2: '101호', created_at: '2026-10-01',
        }],
      });
    }
    if (path === '/kpost-pickup' && method === 'POST') {
      return json(route, { success: true, id: 4, tracking_no: '9876543210987', tracking_nos: ['9876543210987'], is_test: true });
    }
    if (path === '/kpost-pickup' && method === 'GET') return json(route, { items: [KPOST_ITEM] });
    if (path === '/overseas-shipping/meta') {
      return json(route, {
        live_ready: false,
        methods: [{ code: 'EMS', name: 'EMS', desc: 'EMS', premiumcd: '31', em_ee: 'em' }],
        sender: { name: '스프링', addr: '대구', zip: '41940', addr1: 'Daegu', addr2: 'Jung', addr3: '394', tel: '01012345678' },
        item_categories: [],
        saved_hs: [{ id: 1, label: '의류', name_ko: '의류', name_en: 'T-shirt', hs_code: '6109', group_name: '의류', origin_country: 'KR' }],
      });
    }
    if (path === '/overseas-shipping/nations') {
      return json(route, { items: [{ nationcd: 'JP', nationnm: '일본', nationfn: 'JAPAN' }], fallback: false });
    }
    if (path === '/overseas-shipping/saved-senders') {
      return json(route, { items: [{ id: 1, label: '창고', name: '스프링', phone: '01012345678', zipcode: '41940', addr1: 'Daegu', addr2: 'Jung', addr3: '394', is_default: true }] });
    }
    if (path === '/overseas-shipping/saved-addresses') {
      return json(route, { items: [{ id: 2, label: '도쿄', recipient_name: 'Taro', recipient_phone: '090', recipient_email: '', countrycd: 'JP', zipcode: '1000001', addr1: 'Tokyo', addr2: 'Chiyoda', addr3: '1-1', is_default: true, created_at: '2026-10-01' }] });
    }
    if (path === '/overseas-shipping/saved-hs') {
      return json(route, { items: [{ id: 1, label: '의류', name_ko: '의류', name_en: 'T-shirt', hs_code: '6109', group_name: '의류', origin_country: 'KR' }] });
    }
    if (path === '/overseas-shipping/quote') {
      return json(route, {
        ok: true,
        totalFee: 18000,
        live: false,
        source: 'test',
        shipping_method: 'EMS',
        shipping_method_name: 'EMS',
        payableTotal: 64000,
        parcel: { ok: true, totalFee: 18000, totweight: 500, em_ee: 'em', error: null },
        document: { ok: true, totalFee: 12000, totweight: 200, em_ee: 'ee', error: null },
        duty: {
          eligible: true,
          dutyPrepaid: true,
          ddpPath: 'postal',
          estimateUsd: 32,
          depositKrw: 46000,
          bufferKrw: 4154,
          usdKrwRate: 1400,
          customsValueUsd: 150,
          ineligibleReason: null,
          breakdown: { dutyUsd: 25.5, serviceFeeUsd: 3.59, bufferUsd: 2.909, totalUsd: 31.999 },
          formula: [
            { label: '관세', expr: 'USD 150.00 × 17%', value: 'USD 25.50' },
            { label: '운송사 수수료', expr: 'USD 1.04 + 관세 USD 25.50 × 10%', value: 'USD 3.59' },
            { label: '버퍼 10%', expr: '추정액 USD 29.0900 × 10%', value: 'USD 2.9090' },
            { label: '원화 환산', expr: 'USD 31.9990 × 1,400원 × 1.02', value: '45,694.57원' },
            { label: '1,000원 올림', expr: '선납 예상금액', value: '46,000원' },
          ],
        },
      });
    }
    if (path === '/overseas-shipping/preview' && method === 'POST') {
      return json(route, { ok: true, preview: { sender_name: '스프링', recipient_name: 'Taro', expected_fee: 18000, countrycd: 'JP', contents_label: '의류' } });
    }
    if (path === '/overseas-shipping' && method === 'POST') {
      return json(route, { success: true, id: 9, tracking_no: 'EG123456789KR', ems_fee: '18000', is_test: true });
    }
    if (path === '/overseas-shipping' && method === 'GET') {
      return json(route, { items: [{ id: 9, tracking_no: 'EG123456789KR', recipient_name: 'Taro', countrycd: 'JP', status: 'requested', is_test: true }] });
    }
    if (path === '/overseas-shipping/9') return json(route, { id: 9, tracking_no: 'EG123456789KR', recipient_name: 'Taro', countrycd: 'JP', status: 'requested', is_test: true, items: [] });
    if (path === '/insights/summary' || path === '/insights/invoice-summary') {
      return json(route, {
        total_orders: 3,
        total_qty: 10,
        total_vendors: 1,
        total_amount: 1000,
        periods: [],
        total_invoices: 0,
        total_storage_fee: 0,
        total_courier_fee: 0,
        total_basic_shipping: 0,
        total_box_fee: 0,
        category_breakdown: [],
        vendor_breakdown: [],
      });
    }
    if (path.startsWith('/insights/')) return json(route, []);
    if (path.startsWith('/rates/')) return json(route, []);
    if (path === '/estimate-analytics/stats') {
      const zeros = {
        total_visits: 0, unique_visitors: 0, total_calculations: 0, conversion_rate: 0,
        mobile_count: 0, mobile_rate: 0, avg_duration_seconds: 0, max_duration_seconds: 0,
      };
      return json(route, {
        summary: zeros,
        os_stats: [], browser_stats: [], device_stats: [], referrer_stats: [],
        location_stats: [], utm_campaign_stats: [], brand_stats: [], hourly_stats: [],
        daily_visits: [], daily_calculations: [],
      });
    }
    if (path === '/settings/company' && method === 'GET') {
      return json(route, { company_name: '스프링풀필먼트', business_no: '123-45-67890' });
    }
    if (path === '/leave/summary') {
      return json(route, {
        total_days: 15, used_days: 1, pending_days: 0, remaining_days: 14,
        total_hours: 105, used_hours: 7, pending_hours: 0, remaining_hours: 98,
        exempt: false, no_join_date: false,
        work_year_start: '2026-01-01', work_year_end: '2026-12-31',
      });
    }
    if (path === '/leave/calendar') {
      return json(route, { year: 2026, month: 10, days: {}, holidays: {} });
    }
    if (path === '/leave/requests' || path === '/leave/pending-approvals' || path === '/leave/approval-history' || path === '/leave/admin/all' || path === '/leave/admin/requests' || path === '/leave/approval-chain' || path === '/leave/approver-candidates') {
      return json(route, []);
    }
    if (path === '/vendors' && method === 'GET') return json(route, []);
    if (path === '/invoices' && method === 'GET') {
      return json(route, {
        invoices: [{
          invoice_id: 1, vendor_id: '1', vendor: '스프링',
          period_from: '2026-09-01', period_to: '2026-09-30',
          total_amount: 1000, status: 'draft', created_at: '2026-10-01',
          modified_by: null, modified_at: null, confirmed_by: null, confirmed_at: null,
        }],
        sum_amount: 1000,
        periods: ['2026-09'],
      });
    }
    if (path.startsWith('/work-log/stats')) {
      return json(route, { total: 0, total_amount: 0, today: 0, by_vendor: [], by_source: [] });
    }
    if (path.startsWith('/work-log')) {
      return json(route, { logs: [], total: 0, filters: { vendors: [], work_types: [], authors: [], sources: [] } });
    }
    if (path.startsWith('/defect-log/stats')) {
      return json(route, { total: 0, today: 0, unresolved: 0, by_result: [] });
    }
    if (path.startsWith('/defect-log')) {
      return json(route, { logs: [], total: 0, filters: { vendors: [], defects: [], authors: [] } });
    }
    if (path === '/repair-log/catalog') return json(route, { work_types: [], defects: [] });
    if (path.startsWith('/repair-log/stats')) {
      return json(route, { total: 0, total_amount: 0, today: 0, by_source: [] });
    }
    if (path.startsWith('/repair-log')) {
      return json(route, { logs: [], total: 0, filters: { vendors: [], work_types: [], defects: [], authors: [] } });
    }
    if (/^\/overseas-shipping\/\d+\/label$/.test(path)) {
      return json(route, { ok: true, label: { order_no: 'EG123456789KR', tracking_no: 'EG123456789KR' } });
    }
    if (path.startsWith('/inbound/share/')) {
      return json(route, {
        batch: {
          id: '1', vendor: '스프링', inbound_date: '2026-10-01', status: 'open', status_label: '입고중',
          wholesale: null, janggi_date: null, janggi_no: null, janggi_url: null, phase: 'open', closed_at: null,
        },
        summary: {
          expected_qty: 1, received_qty: 1, missing_qty: 0, pending_qty: 0, normal_qty: 1,
          defect_pending_qty: 0, repairing_qty: 0, repaired_good_qty: 0, unrecoverable_qty: 0,
          final_good_qty: 1, inbound_progress: 100, processing_progress: 100,
        },
        items: [],
        timeline: [],
        photos: { janggi: null },
        expires_at: '2026-12-01',
        updated_at: '2026-10-04',
      });
    }
    if (path === '/inbound/filter-options') {
      return json(route, { vendors: [], wholesales: [], alias_groups: [] });
    }
    if (path === '/inbound/batches' && method === 'GET') return json(route, { items: [], total: 0 });
    if (path.startsWith('/inbound/batches/')) return json(route, { id: 1, items: [], vendor: '스프링', status: 'open' });

    if (method === 'GET') {
      return json(route, { items: [], uploads: [], invoices: [], success: true, ok: true, total: 0 });
    }
    return json(route, { success: true, ok: true, id: 1 });
  });

  return calls;
}

export function countCalls(calls: ApiCall[], method: string, path: string) {
  return calls.filter((call) => call.method === method && call.path === path).length;
}
