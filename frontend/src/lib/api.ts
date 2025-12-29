/**
 * API 클라이언트
 * FastAPI 백엔드와 통신
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * API 요청 헬퍼
 */
async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

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
export async function uploadFile(file: File, table: string) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('table', table);

  const response = await fetch(`${API_BASE}/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || `Upload Error: ${response.status}`);
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
  return fetchApi<{
    success: boolean;
    message: string;
  }>(`/upload/${uploadId}`, {
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
 * 사용 가능한 별칭 조회
 */
export async function getAvailableAliases(fileType: string, excludeVendor?: string) {
  const query = excludeVendor ? `?exclude_vendor=${encodeURIComponent(excludeVendor)}` : '';
  return fetchApi<string[]>(`/vendors/aliases/available/${fileType}${query}`);
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

