import { fetchApi } from './client';

export interface KpostPickupBoxSize {
  code: string;
  label: string;
  desc: string;
  weight: number;
  volume: number;
}

export interface KpostPickupItem {
  id: number;
  vendor: string;
  order_no: string;
  recipient_name: string;
  recipient_phone: string;
  zipcode: string;
  addr1: string;
  addr2: string;
  pickup_date: string;
  goods_name: string;
  box_size: string;
  box_quantity: number;
  notes: string;
  tracking_no: string;
  req_no: string;
  res_no: string;
  res_date: string;
  price: string;
  post_office: string;
  treat_status: string;
  treat_status_name: string;
  status: string;
  is_test: boolean;
  created_by: string;
  created_at: string;
  canceled_at: string | null;
  canceled_by: string | null;
}

export interface KpostPickupPreview {
  vendor: string;
  recipient_name: string;
  recipient_phone: string;
  zipcode: string;
  addr1: string;
  addr2: string;
  pickup_date: string;
  goods_name: string;
  box_quantity: number;
  box_size: string;
  box_label: string;
  notes: string;
  center_name: string;
  center_addr: string;
  office_ser?: string;
  is_test: boolean;
}

export interface KpostPickupPayload {
  recipient_name: string;
  recipient_phone: string;
  zipcode: string;
  addr1: string;
  addr2: string;
  pickup_date: string;
  goods_name: string;
  box_size: string;
  box_quantity?: number;
  notes: string;
  confirm?: boolean;
  test_mode?: boolean;
}

function pickupQuery(token: string, extra = '') {
  return `?token=${encodeURIComponent(token)}${extra}`;
}

export async function getKpostPickupFilterOptions(token: string) {
  return fetchApi<{ created_by: string[]; recipient_names: string[] }>(
    `/kpost-pickup/filter-options${pickupQuery(token)}`
  );
}

export async function getKpostPickupMeta(token: string) {
  return fetchApi<{
    vendor: string;
    default_pickup_date: string;
    max_pickup_date: string;
    today: string;
    box_sizes: KpostPickupBoxSize[];
    live_ready: boolean;
    office_ser?: string;
    center: { name: string; addr: string };
  }>(`/kpost-pickup/meta${pickupQuery(token)}`);
}

export async function previewKpostPickup(token: string, payload: KpostPickupPayload) {
  return fetchApi<{ ok: boolean; preview: KpostPickupPreview }>(
    `/kpost-pickup/preview${pickupQuery(token)}`,
    { method: 'POST', body: JSON.stringify(payload) }
  );
}

export async function listKpostPickups(
  token: string,
  filters?: { dateFrom?: string; dateTo?: string; recipientName?: string; createdBy?: string; treatStatus?: string }
) {
  let url = `/kpost-pickup${pickupQuery(token)}`;
  if (filters) {
    const params = new URLSearchParams();
    if (filters.dateFrom) params.set('date_from', filters.dateFrom);
    if (filters.dateTo) params.set('date_to', filters.dateTo);
    if (filters.recipientName) params.set('recipient_name', filters.recipientName);
    if (filters.createdBy) params.set('created_by', filters.createdBy);
    if (filters.treatStatus) params.set('treat_status', filters.treatStatus);
    if (params.toString()) url += `&${params.toString()}`;
  }
  return fetchApi<{ items: KpostPickupItem[] }>(url);
}

export async function createKpostPickup(token: string, payload: KpostPickupPayload) {
  const controller = new AbortController();
  // 박스 qty개 × 7초 여유 (최소 20초) — qty만큼 InsertOrder 반복 호출
  const timeoutMs = Math.max(20000, (payload.box_quantity || 1) * 7000);
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetchApi<{
      success: boolean;
      id: number;
      tracking_no: string;
      tracking_nos?: string[];
      is_test: boolean;
      duplicate_guard?: boolean;
      partial?: boolean;
      message?: string;
      pickup_date?: string;
      post_office?: string;
      price?: string;
    }>(`/kpost-pickup${pickupQuery(token)}`, {
      method: 'POST',
      body: JSON.stringify({ ...payload, confirm: true }),
      signal: controller.signal,
    });
  } catch (err) {
    const name = err instanceof Error ? err.name : '';
    const isAbort =
      name === 'AbortError' ||
      (typeof DOMException !== 'undefined' && err instanceof DOMException && err.name === 'AbortError');
    if (isAbort) {
      throw new Error(`우체국 접수 응답이 ${Math.round(timeoutMs / 1000)}초를 넘었습니다. 접수목록에서 송장 생성 여부를 먼저 확인한 뒤 다시 눌러주세요.`);
    }
    throw err;
  } finally {
    window.clearTimeout(timer);
  }
}

export async function cancelKpostPickup(token: string, id: number) {
  return fetchApi<{ success: boolean; already?: boolean; message?: string }>(
    `/kpost-pickup/${id}/cancel${pickupQuery(token, '&confirm=true')}`,
    { method: 'POST' }
  );
}

export async function deleteKpostPickup(token: string, id: number) {
  return fetchApi<{ success: boolean; id: number; tracking_no: string }>(
    `/kpost-pickup/${id}${pickupQuery(token)}`,
    { method: 'DELETE' }
  );
}

export async function bulkDeleteKpostPickups(token: string, trackingNos: string[]) {
  return fetchApi<{ success: boolean; deleted: number; tracking_nos: string[] }>(
    `/kpost-pickup/bulk-delete${pickupQuery(token)}`,
    { method: 'POST', body: JSON.stringify(trackingNos) }
  );
}

export async function refreshKpostPickupStatuses(token: string) {
  return fetchApi<{
    success: boolean;
    checked: number;
    completed: number;
    failed: number;
    message?: string;
  }>(`/kpost-pickup/refresh-status${pickupQuery(token)}`, { method: 'POST' });
}

export async function patchKpostTreatStatus(token: string, id: number, treatStatus: string) {
  return fetchApi<{ success: boolean; treat_status: string; treat_status_name: string }>(
    `/kpost-pickup/${id}/treat-status?token=${token}&treat_status=${treatStatus}`,
    { method: 'PATCH' },
  );
}

export interface SavedRecipient {
  id: number;
  label: string;
  recipient_name: string;
  recipient_phone: string;
  zipcode: string;
  addr1: string;
  addr2: string;
  created_at: string;
}

export interface SavedRecipientPayload {
  label: string;
  recipient_name: string;
  recipient_phone: string;
  zipcode: string;
  addr1: string;
  addr2: string;
}

export async function listSavedRecipients(token: string) {
  return fetchApi<{ items: SavedRecipient[] }>(`/kpost-pickup/saved-recipients${pickupQuery(token)}`);
}

export async function saveRecipient(token: string, payload: SavedRecipientPayload) {
  return fetchApi<SavedRecipient & { success: boolean }>(
    `/kpost-pickup/saved-recipients${pickupQuery(token)}`,
    { method: 'POST', body: JSON.stringify(payload) }
  );
}

export async function updateSavedRecipient(token: string, id: number, payload: SavedRecipientPayload) {
  return fetchApi<{ success: boolean; id: number; label: string }>(
    `/kpost-pickup/saved-recipients/${id}${pickupQuery(token)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }
  );
}

export async function deleteSavedRecipient(token: string, id: number) {
  return fetchApi<{ success: boolean; id: number }>(
    `/kpost-pickup/saved-recipients/${id}${pickupQuery(token)}`,
    { method: 'DELETE' }
  );
}
