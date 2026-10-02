import { fetchApi } from './client';

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
