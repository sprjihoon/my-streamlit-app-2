import { API_BASE, fetchApi } from './client';

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
