import { fetchApi } from './client';

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
