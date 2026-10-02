import { fetchApi } from './client';

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
