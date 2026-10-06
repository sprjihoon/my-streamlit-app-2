import { API_BASE, fetchApi } from './client';

function domesticQuery(token: string, extra = '') {
  return `?token=${encodeURIComponent(token)}${extra}`;
}

export interface DomesticVendor {
  id: number;
  name: string;
  office_ser: string;
  sender_name: string;
  sender_phone: string;
  sender_zip: string;
  sender_addr1: string;
  sender_addr2: string;
}

export interface DomesticBoxSize {
  code: string;
  label: string;
  desc: string;
  weight: number;
  volume: number;
}

export interface DomesticParty {
  name: string;
  phone: string;
  zip: string;
  addr1: string;
  addr2: string;
}

export interface DomesticPreview {
  vendor_name: string;
  office_ser: string;
  api_sender: DomesticParty;
  print_sender: DomesticParty;
  recipient: DomesticParty;
  goods_name: string;
  goods_qty: number;
  label_count: number;
  box_size: string;
  box_label: string;
  weight: number;
  volume: number;
}

export interface DomesticShipment {
  id: number;
  vendor_id: number;
  vendor_name: string;
  office_ser: string;
  api_sender_name: string;
  api_sender_phone: string;
  api_sender_zip: string;
  api_sender_addr1: string;
  api_sender_addr2: string;
  print_sender_name: string;
  print_sender_phone: string;
  print_sender_zip: string;
  print_sender_addr1: string;
  print_sender_addr2: string;
  recipient_name: string;
  recipient_phone: string;
  recipient_zip: string;
  recipient_addr1: string;
  recipient_addr2: string;
  goods_name: string;
  goods_qty: number;
  box_size: string;
  weight: number;
  volume: number;
  notes: string;
  order_no: string;
  tracking_no: string;
  price: string;
  post_office: string;
  status: string;
  is_test: boolean;
  treat_status?: string | null;
  treat_status_name?: string | null;
  created_by: string;
  created_at: string;
  canceled_at?: string;
  canceled_by?: string;
}

export interface DomesticSubmitPayload {
  vendor_id: number;
  print_sender_name: string;
  print_sender_phone: string;
  print_sender_zip: string;
  print_sender_addr1: string;
  print_sender_addr2: string;
  recipient_name: string;
  recipient_phone: string;
  recipient_zip: string;
  recipient_addr1: string;
  recipient_addr2: string;
  goods_name: string;
  goods_qty: number;
  box_size: string;
  label_count: number;
  notes: string;
  test_mode: boolean;
}

export async function getDomesticMeta(token: string) {
  return fetchApi<{ live_ready: boolean; box_sizes: DomesticBoxSize[] }>(
    `/domestic-shipping/meta${domesticQuery(token)}`
  );
}

export async function listDomesticVendors(token: string) {
  return fetchApi<{ items: DomesticVendor[] }>(`/domestic-shipping/vendors${domesticQuery(token)}`);
}

export async function saveDomesticVendor(token: string, payload: Omit<DomesticVendor, 'id'>, id?: number) {
  const path = id ? `/domestic-shipping/vendors/${id}` : '/domestic-shipping/vendors';
  return fetchApi<{ success: boolean; id: number }>(`${path}${domesticQuery(token)}`, {
    method: id ? 'PUT' : 'POST',
    body: JSON.stringify(payload),
  });
}

export async function deleteDomesticVendor(token: string, id: number) {
  return fetchApi<{ success: boolean }>(`/domestic-shipping/vendors/${id}${domesticQuery(token)}`, {
    method: 'DELETE',
  });
}

export async function previewDomesticShipping(token: string, payload: DomesticSubmitPayload) {
  return fetchApi<{ ok: boolean; preview: DomesticPreview; live_ready: boolean }>(
    `/domestic-shipping/preview${domesticQuery(token)}`,
    { method: 'POST', body: JSON.stringify(payload) }
  );
}

export async function createDomesticShipping(token: string, payload: DomesticSubmitPayload) {
  const controller = new AbortController();
  const timeoutMs = Math.max(20000, (payload.label_count || 1) * 7000);
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetchApi<{
      success: boolean;
      id: number;
      ids?: number[];
      order_no: string;
      tracking_no: string;
      tracking_nos?: string[];
      price: string;
      is_test: boolean;
      duplicate_guard?: boolean;
      partial?: boolean;
      preview?: DomesticPreview;
    }>(`/domestic-shipping${domesticQuery(token)}`, {
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
      throw new Error(`우체국 접수 응답이 ${Math.round(timeoutMs / 1000)}초를 넘었습니다. 출고 목록에서 송장 생성 여부를 먼저 확인한 뒤 다시 눌러주세요.`);
    }
    throw err;
  } finally {
    window.clearTimeout(timer);
  }
}

export async function listDomesticShipments(token: string) {
  return fetchApi<{ items: DomesticShipment[] }>(`/domestic-shipping${domesticQuery(token)}`);
}

export async function refreshDomesticShippingStatuses(token: string) {
  return fetchApi<{
    success: boolean;
    checked: number;
    delivered: number;
    failed: number;
    message?: string;
  }>(`/domestic-shipping/refresh-status${domesticQuery(token)}`, { method: 'POST' });
}

export async function getDomesticShipment(token: string, id: number) {
  return fetchApi<DomesticShipment>(`/domestic-shipping/${id}${domesticQuery(token)}`);
}

export async function cancelDomesticShipping(token: string, id: number) {
  return fetchApi<{ success: boolean; already?: boolean; message?: string }>(
    `/domestic-shipping/${id}/cancel${domesticQuery(token, '&confirm=true')}`,
    { method: 'POST' }
  );
}

export async function deleteDomesticShipping(token: string, id: number) {
  return fetchApi<{ success: boolean; message?: string }>(
    `/domestic-shipping/${id}${domesticQuery(token)}`,
    { method: 'DELETE' }
  );
}

export function domesticLabelPdfUrl(token: string, id: number) {
  return `${API_BASE}/domestic-shipping/${id}/label${domesticQuery(token, '&format=pdf')}`;
}

export function domesticLabelsPdfUrl(token: string, ids: number[]) {
  return `${API_BASE}/domestic-shipping/labels${domesticQuery(token, `&ids=${ids.join(',')}&format=pdf`)}`;
}

export interface DomesticSavedRecipient {
  id: number;
  label: string;
  recipient_name: string;
  recipient_phone: string;
  zipcode: string;
  addr1: string;
  addr2: string;
  created_at: string;
}

export interface DomesticSavedRecipientPayload {
  label: string;
  recipient_name: string;
  recipient_phone: string;
  zipcode: string;
  addr1: string;
  addr2: string;
}

export async function listDomesticSavedRecipients(token: string) {
  return fetchApi<{ items: DomesticSavedRecipient[] }>(
    `/domestic-shipping/saved-recipients${domesticQuery(token)}`
  );
}

export async function saveDomesticRecipient(token: string, payload: DomesticSavedRecipientPayload) {
  return fetchApi<DomesticSavedRecipient & { success: boolean }>(
    `/domestic-shipping/saved-recipients${domesticQuery(token)}`,
    { method: 'POST', body: JSON.stringify(payload) }
  );
}

export async function updateDomesticSavedRecipient(
  token: string,
  id: number,
  payload: DomesticSavedRecipientPayload,
) {
  return fetchApi<{ success: boolean; id: number; label: string }>(
    `/domestic-shipping/saved-recipients/${id}${domesticQuery(token)}`,
    { method: 'PUT', body: JSON.stringify(payload) }
  );
}

export async function deleteDomesticSavedRecipient(token: string, id: number) {
  return fetchApi<{ success: boolean; id: number }>(
    `/domestic-shipping/saved-recipients/${id}${domesticQuery(token)}`,
    { method: 'DELETE' }
  );
}
