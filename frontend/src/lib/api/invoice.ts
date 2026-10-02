import { fetchApi } from './client';

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
