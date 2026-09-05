/**
 * API 클라이언트
 * FastAPI 백엔드와 통신
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/** 브라우저에서 사용할 API 베이스 URL (연결 확인용) */
export function getApiBase(): string {
  return API_BASE;
}

/**
 * API 요청 헬퍼
 * - 네트워크 실패 시 "Failed to fetch" 대신 안내 메시지 반환
 */
async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;

  let response: Response;
  try {
    response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      ...options,
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (msg === 'Failed to fetch' || msg.includes('NetworkError') || msg.includes('Load failed')) {
      throw new Error(
        `서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.`
      );
    }
    throw e;
  }

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || `API Error: ${response.status}`);
  }

  return response.json();
}

/**
 * 헬스체크
 */
export async function checkHealth() {
  return fetchApi<{ status: string; version: string }>('/health');
}

/**
 * 인보이스 계산
 */
export async function calculateInvoice(params: {
  vendor: string;
  date_from: string;
  date_to: string;
  include_basic_shipping?: boolean;
  include_courier_fee?: boolean;
  include_inbound_fee?: boolean;
  include_remote_fee?: boolean;
  include_worklog?: boolean;
}) {
  return fetchApi<{
    success: boolean;
    vendor: string;
    date_from: string;
    date_to: string;
    items: Array<{
      항목: string;
      수량: number;
      단가: number;
      금액: number;
      비고?: string;
    }>;
    total_amount: number;
    warnings: string[];
  }>('/calculate', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

/** 물류 견적 항목 타입 */
export interface EstimateItem {
  항목: string;
  수량: number;
  단가: number;
  금액: number;
  비고?: string;
}

/**
 * 견적 추가 작업용 청구서 항목 목록 (out_extra + material_rates)
 */
export async function getChargeableItems() {
  return fetchApi<{ items: Array<{ item_name: string; unit_price: number; source: string }> }>(
    '/estimate/chargeable-items'
  );
}

/**
 * 물류 견적 계산
 */
export async function calculateEstimate(params: {
  company_name?: string;
  contact?: string;
  email?: string;
  monthly_outbound: number;
  rate_type?: string;
  zone_ratios?: Record<string, number>;
  return_percentage?: number;
  inbound_qty?: number;
  combined_percentage?: number;
  combined_avg_qty?: number;
  brand_type?: 'fashion' | 'beauty' | 'etc';
  need_quality_work?: boolean;
  pp_bag_provider?: 'brand' | 'ours';
  mailer_provider?: 'brand' | 'ours';
  courier_box_provider?: 'brand' | 'ours';
  need_tex_work?: boolean;
  need_barcode_attach?: boolean;
  need_void_work?: boolean;
  need_video_out?: boolean;
  need_video_ret?: boolean;
  need_sticker_attach?: boolean;
  need_leaflet_insert?: boolean;
  need_b2b_document?: boolean;
  storage_plt?: number;
  sku_count?: number;
  extra_work_entries?: Array<{ item_name: string; qty: number }>;
  work_log_entries?: Array<{ 분류: string; 수량: number; 단가: number }>;
}) {
  return fetchApi<{
    success: boolean;
    items: EstimateItem[];
    total_amount: number;
    company_name: string;
    contact: string;
    email: string;
    warnings: string[];
  }>('/estimate', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

/**
 * 견적서 PDF 출력 (업체명·연락처·이메일 반영)
 * @returns Blob (PDF)
 */
export async function exportEstimatePdf(body: {
  company_name: string;
  contact: string;
  email: string;
  items: EstimateItem[];
  total_amount: number;
  brand_type?: string;
}): Promise<Blob> {
  const url = `${API_BASE}/estimate/export/pdf`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `PDF export failed: ${response.status}`);
  }
  return response.blob();
}

/**
 * 택배요금 계산
 */
export async function calculateCourierFee(params: {
  vendor: string;
  date_from: string;
  date_to: string;
}) {
  return fetchApi<{
    success: boolean;
    vendor: string;
    zone_counts: Record<string, number>;
    items: Array<{
      항목: string;
      수량: number;
      단가: number;
      금액: number;
    }>;
  }>('/calculate/courier-fee', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

/**
 * 배송통계 조회
 */
export async function getShippingStats(params: {
  vendor: string;
  date_from: string;
  date_to: string;
}) {
  return fetchApi<{
    success: boolean;
    vendor: string;
    count: number;
    data: Record<string, unknown>[];
  }>('/calculate/shipping-stats', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

/**
 * 파일 업로드
 */
export async function uploadFile(file: File, table: string, token?: string) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('table', table);
  if (token) {
    formData.append('token', token);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/upload`, {
      method: 'POST',
      body: formData,
      // FormData를 사용할 때는 Content-Type을 설정하지 않아야 브라우저가 자동으로 boundary를 추가합니다
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (msg === 'Failed to fetch' || msg.includes('NetworkError') || msg.includes('Load failed')) {
      throw new Error('서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.');
    }
    throw e;
  }

  if (!response.ok) {
    let errorMessage = `Upload Error: ${response.status}`;
    try {
      const errorData = await response.json();
      errorMessage = errorData.detail || errorData.message || errorMessage;
    } catch {
      const errorText = await response.text();
      errorMessage = errorText || errorMessage;
    }
    throw new Error(errorMessage);
  }

  return response.json() as Promise<{
    success: boolean;
    message: string;
    filename?: string;
  }>;
}

/**
 * 업로드 목록 조회
 */
export async function getUploadList() {
  return fetchApi<{
    success: boolean;
    uploads: Array<{
      id: number;
      filename: string;
      원본명: string;
      table_name: string;
      시작일: string;
      종료일: string;
      업로드시각: string;
    }>;
  }>('/upload/list');
}

/**
 * 업로드 기록 삭제
 */
export async function deleteUpload(uploadId: number) {
  // localStorage에서 토큰 가져오기
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const queryParam = token ? `?token=${encodeURIComponent(token)}` : '';
  
  return fetchApi<{
    success: boolean;
    message: string;
  }>(`/upload/${uploadId}${queryParam}`, {
    method: 'DELETE',
  });
}

/**
 * 테이블 데이터 초기화
 */
export async function resetTableData(tableName: string) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const queryParam = token ? `?token=${encodeURIComponent(token)}` : '';
  
  return fetchApi<{
    success: boolean;
    message: string;
  }>(`/upload/table/${tableName}${queryParam}`, {
    method: 'DELETE',
  });
}

/**
 * 특정 기간 데이터만 삭제
 */
export async function resetTableDataByPeriod(
  tableName: string,
  dateFrom: string,
  dateTo: string,
) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
  if (token) params.set('token', token);

  return fetchApi<{
    success: boolean;
    message: string;
  }>(`/upload/table/${tableName}/period?${params.toString()}`, {
    method: 'DELETE',
  });
}

// ─────────────────────────────────────
// Vendors API
// ─────────────────────────────────────

export interface Vendor {
  vendor: string;
  name: string | null;
  rate_type: string | null;
  sku_group: string | null;
  active: string | null;
  barcode_f: string | null;
  custbox_f: string | null;
  void_f: string | null;
  pp_bag_f: string | null;
  mailer_f: string | null;
  video_out_f: string | null;
  video_ret_f: string | null;
}

export interface VendorDetail extends Vendor {
  alias_inbound_slip: string[];
  alias_shipping_stats: string[];
  alias_kpost_in: string[];
  alias_kpost_ret: string[];
  alias_work_log: string[];
}

export interface UnmatchedAlias {
  file_type: string;
  aliases: string[];
  count: number;
}

/**
 * 거래처 목록 조회
 */
export async function getVendors(activeOnly: boolean = false) {
  const query = activeOnly ? '?active_only=true' : '';
  return fetchApi<Vendor[]>(`/vendors${query}`);
}

/**
 * 매핑 현황 요약 조회
 */
export interface MappingSummary {
  vendor: string;
  name: string;
  active: string;
  inbound_slip: string[];
  shipping_stats: string[];
  kpost_in: string[];
  kpost_ret: string[];
  work_log: string[];
}

export async function getMappingSummary() {
  return fetchApi<MappingSummary[]>('/vendors/mapping-summary');
}

/**
 * 거래처 상세 조회
 */
export async function getVendor(vendorId: string) {
  return fetchApi<VendorDetail>(`/vendors/${encodeURIComponent(vendorId)}`);
}

/**
 * 거래처 생성/수정
 */
export async function saveVendor(data: {
  vendor: string;
  name: string;
  rate_type?: string;
  sku_group?: string;
  active?: string;
  barcode_f?: string;
  custbox_f?: string;
  void_f?: string;
  pp_bag_f?: string;
  mailer_f?: string;
  video_out_f?: string;
  video_ret_f?: string;
  alias_inbound_slip?: string[];
  alias_shipping_stats?: string[];
  alias_kpost_in?: string[];
  alias_kpost_ret?: string[];
  alias_work_log?: string[];
}) {
  return fetchApi<{ status: string; action: string; vendor: string }>('/vendors', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * 거래처 삭제
 */
export async function deleteVendor(vendorId: string) {
  return fetchApi<{ status: string; deleted: string }>(`/vendors/${encodeURIComponent(vendorId)}`, {
    method: 'DELETE',
  });
}

/**
 * 미매칭 별칭 조회
 */
export async function getUnmatchedAliases() {
  return fetchApi<UnmatchedAlias[]>('/vendors/aliases/unmatched');
}

/**
 * 사용 가능한 별칭 조회 (미매핑된 것만)
 */
export async function getAvailableAliases(fileType: string, excludeVendor?: string) {
  const query = excludeVendor ? `?exclude_vendor=${encodeURIComponent(excludeVendor)}` : '';
  return fetchApi<string[]>(`/vendors/aliases/available/${fileType}${query}`);
}

/**
 * 거래처 수정용 별칭 조회 (매핑된 것 + 사용 가능한 것)
 */
export async function getAliasesForVendor(vendorId: string, fileType: string) {
  return fetchApi<{ mapped: string[]; available: string[] }>(
    `/vendors/aliases/for-vendor/${encodeURIComponent(vendorId)}/${fileType}`
  );
}

// ─────────────────────────────────────
// Rates API
// ─────────────────────────────────────

export interface OutBasicRate {
  sku_group: string;
  단가: number;
}

export interface OutExtraRate {
  항목: string;
  단가: number;
}

export interface ShippingZoneRate {
  요금제: string;
  구간: string;
  len_min_cm: number;
  len_max_cm: number;
  요금: number;
}

export interface MaterialRate {
  항목: string;
  단가: number;
}

/**
 * 출고비 요금표 조회
 */
export async function getOutBasicRates() {
  return fetchApi<OutBasicRate[]>('/rates/out_basic');
}

/**
 * 출고비 요금표 저장
 */
export async function saveOutBasicRates(rates: OutBasicRate[]) {
  return fetchApi<{ status: string; count: number }>('/rates/out_basic', {
    method: 'POST',
    body: JSON.stringify(rates),
  });
}

/**
 * 추가 작업 단가 조회
 */
export async function getOutExtraRates() {
  return fetchApi<OutExtraRate[]>('/rates/out_extra');
}

/**
 * 추가 작업 단가 저장
 */
export async function saveOutExtraRates(rates: OutExtraRate[]) {
  return fetchApi<{ status: string; count: number }>('/rates/out_extra', {
    method: 'POST',
    body: JSON.stringify(rates),
  });
}

/**
 * 배송 요금 구간 조회
 */
export async function getShippingZoneRates(rateType?: string) {
  const query = rateType ? `?rate_type=${encodeURIComponent(rateType)}` : '';
  return fetchApi<ShippingZoneRate[]>(`/rates/shipping_zone${query}`);
}

/**
 * 배송 요금 구간 저장
 */
export async function saveShippingZoneRates(rates: ShippingZoneRate[], rateType?: string) {
  const query = rateType ? `?rate_type=${encodeURIComponent(rateType)}` : '';
  return fetchApi<{ status: string; count: number }>(`/rates/shipping_zone${query}`, {
    method: 'POST',
    body: JSON.stringify(rates),
  });
}

/**
 * 부자재 요금표 조회
 */
export async function getMaterialRates() {
  return fetchApi<MaterialRate[]>('/rates/material_rates');
}

/**
 * 부자재 요금표 저장
 */
export async function saveMaterialRates(rates: MaterialRate[]) {
  return fetchApi<{ status: string; count: number }>('/rates/material_rates', {
    method: 'POST',
    body: JSON.stringify(rates),
  });
}

// ─────────────────────────────────────
// Insights API
// ─────────────────────────────────────

export interface InsightsSummary {
  total_orders: number;
  total_qty: number;
  total_vendors: number;
  total_amount: number;
  periods: string[];
}

export interface TopProduct {
  rank: number;
  product: string;
  quantity: number;
}

export interface TopVendorByQty {
  rank: number;
  vendor: string;
  total_qty: number;
  order_count: number;
  avg_qty_per_order: number;
}

export interface TopVendorByRevenue {
  rank: number;
  vendor: string;
  total_revenue: number;
  order_count: number;
  avg_order_value: number;
}

export interface MonthlyTrend {
  period: string;
  total_qty: number;
  order_count: number;
  qty_growth: number | null;
  total_revenue?: number;
}

export interface OurRevenueVendor {
  rank: number;
  vendor: string;
  vendor_name: string;
  invoice_count: number;
  total_revenue: number;
  total_orders: number;
  avg_order_value: number;
}

export interface OurRevenue {
  total_invoices: number;
  total_revenue: number;
  total_orders: number;
  avg_order_value: number;
  vendors: OurRevenueVendor[];
  error?: string;
}

/**
 * 인사이트 요약 조회
 */
export async function getInsightsSummary(period?: string) {
  const query = period ? `?period=${encodeURIComponent(period)}` : '';
  return fetchApi<InsightsSummary>(`/insights/summary${query}`);
}

/**
 * 인기 상품 TOP N
 */
export async function getTopProducts(period?: string, limit: number = 20) {
  let query = `?limit=${limit}`;
  if (period) query += `&period=${encodeURIComponent(period)}`;
  return fetchApi<TopProduct[]>(`/insights/top-products${query}`);
}

/**
 * 거래처별 출고량 TOP N
 */
export async function getTopVendorsByQty(period?: string, limit: number = 20) {
  let query = `?limit=${limit}`;
  if (period) query += `&period=${encodeURIComponent(period)}`;
  return fetchApi<TopVendorByQty[]>(`/insights/top-vendors-by-qty${query}`);
}

/**
 * 거래처별 매출 TOP N
 */
export async function getTopVendorsByRevenue(period?: string, limit: number = 20) {
  let query = `?limit=${limit}`;
  if (period) query += `&period=${encodeURIComponent(period)}`;
  return fetchApi<TopVendorByRevenue[]>(`/insights/top-vendors-by-revenue${query}`);
}

/**
 * 월별 트렌드
 */
export async function getMonthlyTrend() {
  return fetchApi<MonthlyTrend[]>('/insights/monthly-trend');
}

/**
 * 우리 매출 분석
 */
export async function getOurRevenue(period?: string) {
  const query = period ? `?period=${encodeURIComponent(period)}` : '';
  return fetchApi<OurRevenue>(`/insights/our-revenue${query}`);
}

/**
 * 거래처 목록 (인사이트용)
 */
export async function getInsightsVendorsList(period?: string) {
  const query = period ? `?period=${encodeURIComponent(period)}` : '';
  return fetchApi<string[]>(`/insights/vendors-list${query}`);
}

/**
 * 상세 검색
 */
export async function searchInsightsData(params: {
  vendor?: string;
  keyword?: string;
  period?: string;
  limit?: number;
}) {
  const queryParts = [];
  if (params.vendor) queryParts.push(`vendor=${encodeURIComponent(params.vendor)}`);
  if (params.keyword) queryParts.push(`keyword=${encodeURIComponent(params.keyword)}`);
  if (params.period) queryParts.push(`period=${encodeURIComponent(params.period)}`);
  if (params.limit) queryParts.push(`limit=${params.limit}`);
  
  const query = queryParts.length > 0 ? `?${queryParts.join('&')}` : '';
  return fetchApi<{
    count: number;
    total_qty: number;
    data: Record<string, unknown>[];
  }>(`/insights/search${query}`);
}

// ─────────────────────────────────────
// Logs API (관리자 전용)
// ─────────────────────────────────────

export interface ActivityLog {
  log_id: number;
  action_type: string;
  target_type: string | null;
  target_id: string | null;
  target_name: string | null;
  user_nickname: string | null;
  details: string | null;
  created_at: string | null;
}

export interface LogFilters {
  action_types: string[];
  target_types: string[];
  users: string[];
}

export interface LogsResponse {
  logs: ActivityLog[];
  total: number;
  filters: LogFilters;
}

export interface LogStats {
  total: number;
  today: number;
  by_action: Array<{ action_type: string; count: number }>;
  by_user: Array<{ user_nickname: string; count: number }>;
}

/**
 * 활동 로그 조회 (관리자만)
 */
export async function getLogs(token: string, params?: {
  period_from?: string;
  period_to?: string;
  action_type?: string;
  target_type?: string;
  user_nickname?: string;
  target_name?: string;
  limit?: number;
}) {
  const queryParts = [`token=${encodeURIComponent(token)}`];
  if (params?.period_from) queryParts.push(`period_from=${encodeURIComponent(params.period_from)}`);
  if (params?.period_to) queryParts.push(`period_to=${encodeURIComponent(params.period_to)}`);
  if (params?.action_type) queryParts.push(`action_type=${encodeURIComponent(params.action_type)}`);
  if (params?.target_type) queryParts.push(`target_type=${encodeURIComponent(params.target_type)}`);
  if (params?.user_nickname) queryParts.push(`user_nickname=${encodeURIComponent(params.user_nickname)}`);
  if (params?.target_name) queryParts.push(`target_name=${encodeURIComponent(params.target_name)}`);
  if (params?.limit) queryParts.push(`limit=${params.limit}`);
  
  const query = `?${queryParts.join('&')}`;
  return fetchApi<LogsResponse>(`/logs${query}`);
}

/**
 * 로그 통계 조회 (관리자만)
 */
export async function getLogStats(token: string) {
  return fetchApi<LogStats>(`/logs/stats?token=${encodeURIComponent(token)}`);
}

// ─────────────────────────────────────
// 작업일지 API
// ─────────────────────────────────────

export interface WorkLog {
  id: number;
  날짜: string | null;
  업체명: string | null;
  분류: string | null;
  단가: number | null;
  수량: number | null;
  합계: number | null;
  비고1: string | null;
  작성자: string | null;
  저장시간: string | null;
  출처: string | null;
  수정자: string | null;
  수정시간: string | null;
}

export interface WorkLogFilters {
  vendors: string[];
  work_types: string[];
  authors: string[];
  sources: string[];
}

export interface WorkLogResponse {
  logs: WorkLog[];
  total: number;
  filters: WorkLogFilters;
}

export interface WorkLogStats {
  total: number;
  total_amount: number;
  today: number;
  by_vendor: Array<{ 업체명: string; count: number; total_amount: number }>;
  by_work_type: Array<{ 분류: string; count: number; total_amount: number }>;
  by_source: Array<{ 출처: string; count: number }>;
}

/**
 * 작업일지 목록 조회
 */
export async function getWorkLogs(params?: {
  period_from?: string;
  period_to?: string;
  vendor?: string;
  work_type?: string;
  author?: string;
  source?: string;
  limit?: number;
  offset?: number;
}) {
  const queryParts: string[] = [];
  if (params?.period_from) queryParts.push(`period_from=${encodeURIComponent(params.period_from)}`);
  if (params?.period_to) queryParts.push(`period_to=${encodeURIComponent(params.period_to)}`);
  if (params?.vendor) queryParts.push(`vendor=${encodeURIComponent(params.vendor)}`);
  if (params?.work_type) queryParts.push(`work_type=${encodeURIComponent(params.work_type)}`);
  if (params?.author) queryParts.push(`author=${encodeURIComponent(params.author)}`);
  if (params?.source) queryParts.push(`source=${encodeURIComponent(params.source)}`);
  if (params?.limit) queryParts.push(`limit=${params.limit}`);
  if (params?.offset) queryParts.push(`offset=${params.offset}`);
  
  const query = queryParts.length > 0 ? `?${queryParts.join('&')}` : '';
  return fetchApi<WorkLogResponse>(`/work-log${query}`);
}

/**
 * 작업일지 통계 조회
 */
export async function getWorkLogStats(params?: {
  period_from?: string;
  period_to?: string;
}) {
  const queryParts: string[] = [];
  if (params?.period_from) queryParts.push(`period_from=${encodeURIComponent(params.period_from)}`);
  if (params?.period_to) queryParts.push(`period_to=${encodeURIComponent(params.period_to)}`);
  
  const query = queryParts.length > 0 ? `?${queryParts.join('&')}` : '';
  return fetchApi<WorkLogStats>(`/work-log/stats${query}`);
}

/**
 * 작업일지 상세 조회
 */
export async function getWorkLog(id: number) {
  return fetchApi<WorkLog>(`/work-log/${id}`);
}

/**
 * 작업일지 생성
 */
export async function createWorkLog(data: {
  날짜: string;
  업체명: string;
  분류: string;
  단가: number;
  수량?: number;
  비고1?: string;
  작성자?: string;
  출처?: string;
}) {
  return fetchApi<{ success: boolean; id: number; message: string }>('/work-log', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * 작업일지 수정
 */
export async function updateWorkLog(id: number, data: {
  날짜?: string;
  업체명?: string;
  분류?: string;
  단가?: number;
  수량?: number;
  비고1?: string;
}) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const q = token ? `?token=${encodeURIComponent(token)}` : '';
  return fetchApi<{ success: boolean; message: string }>(`/work-log/${id}${q}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

/**
 * 작업일지 삭제
 */
export async function deleteWorkLog(id: number) {
  return fetchApi<{ success: boolean; message: string }>(`/work-log/${id}`, {
    method: 'DELETE',
  });
}

// ─────────────────────────────────────
// 수선작업일지
// ─────────────────────────────────────

export interface RepairLog {
  id: number;
  날짜: string | null;
  업체명: string | null;
  제품명: string | null;
  옵션: string | null;
  바코드: string | null;
  불량명: string | null;
  작업: string | null;
  수량: number | null;
  비용: number | null;
  비고: string | null;
  작성자: string | null;
  저장시간: string | null;
  출처: string | null;
  수정자: string | null;
  수정시간: string | null;
  barcode_image: string | null;
  before_image: string | null;
  after_image: string | null;
}

export interface RepairLogFilters {
  vendors: string[];
  work_types: string[];
  defects: string[];
  authors: string[];
}

export interface RepairWorkType {
  작업명: string;
  기본비용: number;
  별칭: string | null;
}

export interface RepairDefect {
  불량명: string;
  별칭: string | null;
}

export interface RepairLogStats {
  total: number;
  total_amount: number;
  today: number;
  by_source: Array<{ 출처: string; count: number }>;
}

export interface RepairBarcode {
  바코드: string;
  업체명: string;
  제품명: string;
  옵션: string | null;
  상품코드: string | null;
  로케이션: string | null;
  상품명: string | null;
  출처: string | null;
  저장시간: string | null;
}

export function repairImageUrl(filename: string | null | undefined): string | null {
  if (!filename) return null;
  return `${API_BASE}/repair-log/image/${encodeURIComponent(filename)}`;
}

export async function getRepairLogs(params?: {
  period_from?: string;
  period_to?: string;
  vendor?: string;
  work_type?: string;
  defect?: string;
  author?: string;
  limit?: number;
  offset?: number;
}) {
  const q = new URLSearchParams();
  if (params?.period_from) q.set('period_from', params.period_from);
  if (params?.period_to) q.set('period_to', params.period_to);
  if (params?.vendor) q.set('vendor', params.vendor);
  if (params?.work_type) q.set('work_type', params.work_type);
  if (params?.defect) q.set('defect', params.defect);
  if (params?.author) q.set('author', params.author);
  if (params?.limit != null) q.set('limit', String(params.limit));
  if (params?.offset != null) q.set('offset', String(params.offset));
  const qs = q.toString();
  return fetchApi<{ logs: RepairLog[]; total: number; filters: RepairLogFilters }>(
    `/repair-log${qs ? `?${qs}` : ''}`
  );
}

export async function getRepairLogStats(params?: { period_from?: string; period_to?: string }) {
  const q = new URLSearchParams();
  if (params?.period_from) q.set('period_from', params.period_from);
  if (params?.period_to) q.set('period_to', params.period_to);
  const qs = q.toString();
  return fetchApi<RepairLogStats>(`/repair-log/stats${qs ? `?${qs}` : ''}`);
}

export async function createRepairLog(data: {
  날짜: string;
  업체명?: string;
  제품명?: string;
  옵션?: string;
  바코드?: string;
  불량명?: string;
  작업: string;
  수량?: number;
  비용: number;
  비고?: string;
  작성자?: string;
  출처?: string;
}) {
  return fetchApi<{ success: boolean; id: number; message: string }>('/repair-log', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateRepairLog(id: number, data: Partial<{
  날짜: string;
  업체명: string;
  제품명: string;
  옵션: string;
  바코드: string;
  불량명: string;
  작업: string;
  수량: number;
  비용: number;
  비고: string;
}>) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const q = token ? `?token=${encodeURIComponent(token)}` : '';
  return fetchApi<{ success: boolean; message: string }>(`/repair-log/${id}${q}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteRepairLog(id: number) {
  return fetchApi<{ success: boolean; message: string }>(`/repair-log/${id}`, {
    method: 'DELETE',
  });
}

export async function uploadRepairPhotos(
  id: number,
  files: { before?: File | null; after?: File | null; barcode?: File | null }
) {
  const form = new FormData();
  if (files.before) form.append('before', files.before);
  if (files.after) form.append('after', files.after);
  if (files.barcode) form.append('barcode', files.barcode);
  const response = await fetch(`${API_BASE}/repair-log/${id}/photos`, { method: 'POST', body: form });
  if (!response.ok) {
    const err = await response.text();
    throw new Error(err || `Upload Error: ${response.status}`);
  }
  return response.json() as Promise<{ success: boolean; message: string }>;
}

export function getRepairLogExportUrl(startDate: string, endDate: string) {
  return `${API_BASE}/repair-log/export?start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}`;
}

export async function getOldRepairPhotos(days = 60) {
  return fetchApi<{ cutoff: string; days: number; logs: number; files: number }>(
    `/repair-log/photos/old?days=${days}`
  );
}

export async function purgeOldRepairPhotos(days = 60) {
  return fetchApi<{ success: boolean; cutoff: string; logs: number; deleted_files: number; message: string }>(
    `/repair-log/photos/purge-old?days=${days}`,
    { method: 'POST' }
  );
}

export async function getRepairBarcodes(params?: {
  q?: string;
  vendor?: string;
  limit?: number;
  offset?: number;
}) {
  const query = new URLSearchParams();
  if (params?.q) query.set('q', params.q);
  if (params?.vendor) query.set('vendor', params.vendor);
  if (params?.limit != null) query.set('limit', String(params.limit));
  if (params?.offset != null) query.set('offset', String(params.offset));
  const qs = query.toString();
  return fetchApi<{
    items: RepairBarcode[];
    total: number;
    filters: { vendors: string[] };
  }>(`/repair-log/barcodes${qs ? `?${qs}` : ''}`);
}

export async function lookupRepairBarcode(barcode: string) {
  return fetchApi<RepairBarcode>(`/repair-log/barcodes/lookup/${encodeURIComponent(barcode)}`);
}

export async function createRepairBarcode(data: {
  바코드: string;
  업체명: string;
  제품명: string;
  옵션?: string;
  상품코드?: string;
  로케이션?: string;
  상품명?: string;
}) {
  return fetchApi<{ success: boolean; message: string }>('/repair-log/barcodes', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateRepairBarcode(barcode: string, data: Partial<{
  업체명: string;
  제품명: string;
  옵션: string;
  상품코드: string;
  로케이션: string;
  상품명: string;
}>) {
  return fetchApi<{ success: boolean; message: string }>(
    `/repair-log/barcodes/${encodeURIComponent(barcode)}`,
    { method: 'PUT', body: JSON.stringify(data) }
  );
}

export async function deleteRepairBarcode(barcode: string) {
  return fetchApi<{ success: boolean; message: string }>(
    `/repair-log/barcodes/${encodeURIComponent(barcode)}`,
    { method: 'DELETE' }
  );
}

export async function uploadRepairBarcodes(file: File) {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch(`${API_BASE}/repair-log/barcodes/upload`, { method: 'POST', body: form });
  if (!response.ok) {
    let msg = `Upload Error: ${response.status}`;
    try {
      const data = await response.json();
      msg = data.detail || data.message || msg;
    } catch {
      msg = (await response.text()) || msg;
    }
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return response.json() as Promise<{
    success: boolean;
    inserted: number;
    updated: number;
    total: number;
    message: string;
  }>;
}

export function getRepairBarcodeTemplateUrl() {
  return `${API_BASE}/repair-log/barcodes/template`;
}

export async function getRepairCatalog() {
  return fetchApi<{ work_types: RepairWorkType[]; defects: RepairDefect[] }>('/repair-log/catalog');
}

export async function getRepairCatalogPrice(workType: string, vendor?: string, product?: string) {
  const q = new URLSearchParams({ work_type: workType });
  if (vendor) q.set('vendor', vendor);
  if (product) q.set('product', product);
  return fetchApi<{
    found: boolean;
    source: string | null;
    작업명: string;
    비용: number | null;
    기본비용: number | null;
    message: string;
  }>(`/repair-log/catalog/price?${q.toString()}`);
}

export async function saveRepairWorkType(data: { 작업명: string; 기본비용: number; 별칭?: string }) {
  return fetchApi<{ success: boolean; message: string }>('/repair-log/catalog/work-types', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function deleteRepairWorkType(name: string) {
  return fetchApi<{ success: boolean; message: string }>(
    `/repair-log/catalog/work-types/${encodeURIComponent(name)}`,
    { method: 'DELETE' }
  );
}

export async function saveRepairDefect(data: { 불량명: string; 별칭?: string }) {
  return fetchApi<{ success: boolean; message: string }>('/repair-log/catalog/defects', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function deleteRepairDefect(name: string) {
  return fetchApi<{ success: boolean; message: string }>(
    `/repair-log/catalog/defects/${encodeURIComponent(name)}`,
    { method: 'DELETE' }
  );
}

// ─────────────────────────────────────
// 청구금액 분석 (Invoice Analytics)
// ─────────────────────────────────────

export interface InvoiceMonthlyTrend {
  period: string;
  invoice_count: number;
  total_amount: number;
  growth: number | null;
}

export interface InvoiceMonthlyCategoryData {
  periods: string[];
  categories: string[];
  data: Record<string, number | string>[];
}

export interface InvoiceMonthlyVendorData {
  periods: string[];
  vendors: string[];
  data: Record<string, number | string>[];
}

export interface InvoiceAnalyticsSummary {
  total_invoices: number;
  total_amount: number;
  total_months: number;
  avg_monthly_amount: number;
  first_period: string | null;
  last_period: string | null;
}

export async function getInvoiceMonthlyTrend() {
  return fetchApi<InvoiceMonthlyTrend[]>('/invoice-analytics/monthly-trend');
}

export async function getInvoiceMonthlyByCategory() {
  return fetchApi<InvoiceMonthlyCategoryData>('/invoice-analytics/monthly-by-category');
}

export async function getInvoiceMonthlyByVendor() {
  return fetchApi<InvoiceMonthlyVendorData>('/invoice-analytics/monthly-by-vendor');
}

export async function getInvoiceAnalyticsSummary() {
  return fetchApi<InvoiceAnalyticsSummary>('/invoice-analytics/summary');
}

