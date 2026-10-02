import { fetchApi } from './client';

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
