import { API_BASE, fetchApi } from './client';

// ─────────────────────────────────────────────────────────────────
// 해외배송 (EMS / K-Packet)
// ─────────────────────────────────────────────────────────────────

export interface OverseasInvoiceItem {
  product_name?: string;
  name_en: string;
  quantity: number;
  unit_price_usd: number;
  hs_code?: string;
  origin_country?: string;
}

export interface OverseasShippingPayload {
  shipping_method: 'EMS' | 'EMS_PREMIUM' | 'KPACKET';
  contents_type?: 'parcel' | 'document';
  customs_gubun?: 'merchandise' | 'gift' | 'sample';
  countrycd: string;
  sender_name?: string;
  sender_zipcode?: string;
  sender_addr1?: string;
  sender_addr2?: string;
  sender_addr3?: string;
  sender_tel?: string;
  receivename: string;
  receivetelno: string;
  receivemail: string;
  receivezipcode: string;
  receiveaddr1: string;
  receiveaddr2: string;
  receiveaddr3: string;
  totweight: number;
  boxlength: number;
  boxwidth: number;
  boxheight: number;
  items: OverseasInvoiceItem[];
  notes: string;
  confirm?: boolean;
  test_mode?: boolean;
  save_address?: boolean;
  save_address_label?: string;
  save_address_default?: boolean;
  save_sender?: boolean;
  save_sender_label?: string;
  save_sender_default?: boolean;
}

export interface OverseasShippingItem {
  id: number;
  order_no: string;
  shipping_method: string;
  premiumcd: string;
  contents_type?: string;
  customs_gubun?: string;
  contents_label?: string;
  countrycd: string;
  sender_name?: string;
  recipient_name: string;
  recipient_phone: string;
  recipient_email: string;
  recipient_zip: string;
  recipient_addr1: string;
  recipient_addr2: string;
  recipient_addr3: string;
  totweight: number;
  boxlength: number;
  boxwidth: number;
  boxheight: number;
  items: OverseasInvoiceItem[];
  sender_zipcode?: string;
  sender_addr1?: string;
  sender_addr2?: string;
  sender_addr3?: string;
  sender_tel?: string;
  tracking_no: string;
  req_no: string;
  receive_seq: string;
  ems_fee: string;
  ddp_krw?: number;
  spent_total?: number;
  post_office: string;
  status: string;
  is_test: boolean;
  notes: string;
  created_by: string;
  created_at: string;
  canceled_at: string | null;
  canceled_by: string | null;
  treat_status?: string | null;
  treat_status_name?: string | null;
  treat_event_at?: string | null;
  treat_office?: string | null;
}

export function overseasStatusLabel(item: {
  status: string;
  is_test: boolean;
  treat_status?: string | null;
}) {
  if (item.status === 'canceled') return '취소';
  if (item.is_test) return '테스트';
  return (item.treat_status || '').trim() || '접수';
}

export interface OverseasShippingPreview {
  shipping_method: string;
  shipping_method_name: string;
  contents_type?: string;
  customs_gubun?: string;
  contents_label?: string;
  em_ee?: string;
  countrycd: string;
  recipient_name: string;
  recipient_phone: string;
  recipient_email: string;
  recipient_zip: string;
  recipient_addr: string;
  totweight: number;
  volume_weight?: number | null;
  chargeable_weight?: number;
  boxlength: number;
  boxwidth: number;
  boxheight: number;
  items: OverseasInvoiceItem[];
  sender_name: string;
  sender_addr: string;
  expected_fee: number | null;
  duty?: OverseasDutyQuote;
  is_test: boolean;
  notes: string;
  text_corrections?: Array<{ field?: string; label: string; before: string; after: string }>;
}

export interface OverseasDutyQuote {
  eligible: boolean;
  dutyPrepaid: boolean;
  ddpPath: 'postal' | 'premium' | null;
  estimateUsd: number;
  depositKrw: number;
  bufferKrw?: number;
  reserveKrw?: number;
  localEstimateKrw?: number | null;
  showsLocalEstimate?: boolean;
  rateConfirmed?: boolean;
  collectionNote?: string | null;
  formula?: Array<{ label: string; expr: string; value: string }>;
  breakdown: {
    dutyUsd: number;
    serviceFeeUsd: number;
    bufferUsd: number;
    totalUsd: number;
  } | null;
  ineligibleReason: string | null;
  usdKrwRate: number;
  customsValueUsd: number;
}

function overseasQuery(token: string, extra = '') {
  return `?token=${encodeURIComponent(token)}${extra}`;
}

export async function getOverseasShippingMeta(token: string) {
  return fetchApi<{
    live_ready: boolean;
    methods: Array<{ code: string; name: string; desc: string; premiumcd: string; em_ee: string }>;
    sender: { name: string; addr: string; zip: string; addr1?: string; addr2?: string; addr3?: string; tel?: string };
    item_categories?: Array<{ id: string; name_ko: string; name_en: string; hs_code: string; group: string }>;
    saved_hs?: OverseasSavedHs[];
  }>(`/overseas-shipping/meta${overseasQuery(token)}`);
}

export async function listOverseasNations(token: string, premiumcd: string) {
  return fetchApi<{
    items: Array<{ nationcd: string; nationnm: string; nationfn: string; premiumcd?: string }>;
    fallback: boolean;
    source?: string;
    count?: number;
  }>(`/overseas-shipping/nations${overseasQuery(token, `&premiumcd=${encodeURIComponent(premiumcd)}`)}`);
}

export type OverseasQuotePart = {
  ok: boolean;
  totalFee: number | null;
  totweight: number;
  actual_weight?: number;
  volume_weight?: number | null;
  chargeable_weight?: number;
  em_ee: string;
  error: string | null;
};

export async function quoteOverseasShipping(
  token: string,
  payload: {
    shipping_method: OverseasShippingPayload['shipping_method'];
    contents_type?: 'parcel' | 'document';
    customs_gubun?: 'merchandise' | 'gift' | 'sample';
    countrycd: string;
    totweight: number;
    boxlength: number;
    boxwidth: number;
    boxheight: number;
    customs_value_usd?: number;
    sender_name?: string;
    duty_items?: Array<{ hs_code?: string; unit_price_usd?: number; quantity?: number; value_usd?: number }>;
  }
) {
  const extra =
    `&shipping_method=${encodeURIComponent(payload.shipping_method)}` +
    `&contents_type=${encodeURIComponent(payload.contents_type || 'parcel')}` +
    `&customs_gubun=${encodeURIComponent(payload.customs_gubun || 'merchandise')}` +
    `&sender_name=${encodeURIComponent(payload.sender_name || '')}` +
    `&countrycd=${encodeURIComponent(payload.countrycd)}` +
    `&totweight=${encodeURIComponent(String(payload.totweight))}` +
    `&boxlength=${encodeURIComponent(String(payload.boxlength || 0))}` +
    `&boxwidth=${encodeURIComponent(String(payload.boxwidth || 0))}` +
    `&boxheight=${encodeURIComponent(String(payload.boxheight || 0))}` +
    `&customs_value_usd=${encodeURIComponent(String(payload.customs_value_usd || 0))}` +
    `&duty_items=${encodeURIComponent(JSON.stringify(payload.duty_items || []))}`;
  return fetchApi<{
    ok: boolean;
    totalFee: number | null;
    live: boolean;
    source: string;
    shipping_method: string;
    shipping_method_name: string;
    contents_type: 'parcel' | 'document';
    contents_label: string;
    em_ee: string;
    countrycd: string;
    totweight: number;
    actual_weight?: number;
    volume_weight?: number | null;
    chargeable_weight?: number;
    error: string | null;
    duty?: OverseasDutyQuote;
    payableTotal?: number | null;
    parcel?: OverseasQuotePart;
    document?: OverseasQuotePart | null;
  }>(`/overseas-shipping/quote${overseasQuery(token, extra)}`);
}

export interface OverseasExcelItem {
  product_name: string;
  name_en: string;
  quantity: number;
  unit_price_usd: number;
  hs_code: string;
  origin_country: string;
}

export interface OverseasExcelGroup {
  bundle_no: string;
  receivename: string;
  receivetelno: string;
  receivemail: string;
  countrycd: string;
  receivezipcode: string;
  receiveaddr1: string;
  receiveaddr2: string;
  receiveaddr3: string;
  notes: string;
  totweight: number;
  boxlength: number;
  boxwidth: number;
  boxheight: number;
  items: OverseasExcelItem[];
  missing: string[];
}

export async function importOverseasExcel(token: string, file: File) {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch(`${API_BASE}/overseas-shipping/import-excel${overseasQuery(token)}`, {
    method: 'POST',
    body: form,
  });
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
  return response.json() as Promise<{ groups: OverseasExcelGroup[] }>;
}

export async function previewOverseasShipping(token: string, payload: OverseasShippingPayload) {
  return fetchApi<{ ok: boolean; preview: OverseasShippingPreview }>(
    `/overseas-shipping/preview${overseasQuery(token)}`,
    { method: 'POST', body: JSON.stringify(payload) }
  );
}

export async function listOverseasShipments(token: string) {
  return fetchApi<{ items: OverseasShippingItem[] }>(`/overseas-shipping${overseasQuery(token)}`);
}

export async function refreshOverseasShippingStatuses(token: string) {
  return fetchApi<{
    success: boolean;
    checked: number;
    delivered: number;
    failed: number;
    message?: string;
  }>(`/overseas-shipping/refresh-status${overseasQuery(token)}`, { method: 'POST' });
}

export async function getOverseasShipment(token: string, id: number) {
  return fetchApi<OverseasShippingItem>(`/overseas-shipping/${id}${overseasQuery(token)}`);
}

export async function createOverseasShipping(token: string, payload: OverseasShippingPayload) {
  return fetchApi<{
    success: boolean;
    id: number;
    order_no: string;
    tracking_no: string;
    ems_fee: string;
    is_test: boolean;
    duplicate_guard?: boolean;
    preview?: OverseasShippingPreview;
  }>(`/overseas-shipping${overseasQuery(token)}`, {
    method: 'POST',
    body: JSON.stringify({ ...payload, confirm: true }),
  });
}

export async function cancelOverseasShipping(token: string, id: number) {
  return fetchApi<{ success: boolean; already?: boolean; message?: string }>(
    `/overseas-shipping/${id}/cancel${overseasQuery(token, '&confirm=true')}`,
    { method: 'POST' }
  );
}

export async function deleteOverseasShipping(token: string, id: number) {
  return fetchApi<{ success: boolean; message?: string }>(
    `/overseas-shipping/${id}${overseasQuery(token)}`,
    { method: 'DELETE' }
  );
}

export interface OverseasLabelData {
  source: string;
  id: number;
  order_no: string;
  shipping_method: string;
  service_label: string;
  contents_type?: string;
  contents_label?: string;
  contents_gubun?: string;
  regino: string;
  ems_applied: boolean;
  is_test: boolean;
  status: string;
  ems_fee: number | null;
  ems_req_no: string | null;
  ems_receive_seq: string | null;
  post_office: string;
  totweight: number;
  boxlength: number;
  boxwidth: number;
  boxheight: number;
  created_at: string;
  sender: { name: string; address: string; zip: string; tel: string; country: string };
  recipient: {
    name: string;
    addr1: string;
    addr2: string;
    addr3: string;
    zip: string;
    phone: string;
    email: string;
    country: string;
    country_name: string;
  };
  items: OverseasInvoiceItem[];
  customs_value_usd: number;
  barcode_url: string;
}

export function overseasLabelHtmlUrl(token: string, id: number) {
  return `${API_BASE}/overseas-shipping/${id}/label${overseasQuery(token, '&format=html')}`;
}

export function overseasLabelPdfUrl(token: string, id: number) {
  return `${API_BASE}/overseas-shipping/${id}/label${overseasQuery(token, '&format=pdf')}`;
}

export async function getOverseasShippingLabel(token: string, id: number) {
  return fetchApi<{ ok: boolean; label: OverseasLabelData }>(
    `/overseas-shipping/${id}/label${overseasQuery(token)}`
  );
}

export interface OverseasSavedAddress {
  id: number;
  label: string;
  recipient_name: string;
  recipient_phone: string;
  recipient_email: string;
  countrycd: string;
  zipcode: string;
  addr1: string;
  addr2: string;
  addr3: string;
  is_default: boolean;
  created_at: string;
}

export interface OverseasSavedAddressPayload {
  label: string;
  recipient_name: string;
  recipient_phone?: string;
  recipient_email?: string;
  countrycd: string;
  zipcode?: string;
  addr1?: string;
  addr2?: string;
  addr3: string;
  is_default?: boolean;
}

export async function listOverseasSavedAddresses(token: string) {
  return fetchApi<{ items: OverseasSavedAddress[] }>(
    `/overseas-shipping/saved-addresses${overseasQuery(token)}`
  );
}

export async function saveOverseasAddress(token: string, payload: OverseasSavedAddressPayload) {
  return fetchApi<OverseasSavedAddress & { success: boolean }>(
    `/overseas-shipping/saved-addresses${overseasQuery(token)}`,
    { method: 'POST', body: JSON.stringify(payload) }
  );
}

export async function deleteOverseasSavedAddress(token: string, id: number) {
  return fetchApi<{ success: boolean; id: number }>(
    `/overseas-shipping/saved-addresses/${id}${overseasQuery(token)}`,
    { method: 'DELETE' }
  );
}

export async function updateOverseasSavedAddress(token: string, id: number, payload: OverseasSavedAddressPayload) {
  return fetchApi<{ success: boolean; id: number; label: string }>(
    `/overseas-shipping/saved-addresses/${id}${overseasQuery(token)}`,
    { method: 'PUT', body: JSON.stringify(payload) }
  );
}

export interface OverseasSavedSender {
  id: number;
  label: string;
  name: string;
  phone: string;
  zipcode: string;
  addr1: string;
  addr2: string;
  addr3: string;
  is_default: boolean;
  created_at: string;
}

export interface OverseasSavedSenderPayload {
  label: string;
  name: string;
  phone?: string;
  zipcode?: string;
  addr1?: string;
  addr2?: string;
  addr3?: string;
  is_default?: boolean;
}

export async function listOverseasSavedSenders(token: string) {
  return fetchApi<{ items: OverseasSavedSender[] }>(
    `/overseas-shipping/saved-senders${overseasQuery(token)}`
  );
}

export async function saveOverseasSender(token: string, payload: OverseasSavedSenderPayload) {
  return fetchApi<OverseasSavedSender & { success: boolean }>(
    `/overseas-shipping/saved-senders${overseasQuery(token)}`,
    { method: 'POST', body: JSON.stringify(payload) }
  );
}

export async function updateOverseasSavedSender(token: string, id: number, payload: OverseasSavedSenderPayload) {
  return fetchApi<{ success: boolean; id: number; label: string }>(
    `/overseas-shipping/saved-senders/${id}${overseasQuery(token)}`,
    { method: 'PUT', body: JSON.stringify(payload) }
  );
}

export async function deleteOverseasSavedSender(token: string, id: number) {
  return fetchApi<{ success: boolean; id: number }>(
    `/overseas-shipping/saved-senders/${id}${overseasQuery(token)}`,
    { method: 'DELETE' }
  );
}

export interface OverseasSavedHs {
  id: number;
  label: string;
  name_ko: string;
  name_en: string;
  hs_code: string;
  origin_country: string;
  group_name: string;
  created_at: string;
}

export interface OverseasSavedHsPayload {
  label?: string;
  name_ko?: string;
  name_en: string;
  hs_code: string;
  origin_country?: string;
  group_name?: string;
}

export async function listOverseasSavedHs(token: string, q = '') {
  return fetchApi<{ items: OverseasSavedHs[] }>(
    `/overseas-shipping/saved-hs${overseasQuery(token, q ? `&q=${encodeURIComponent(q)}` : '')}`
  );
}

export async function saveOverseasHs(token: string, payload: OverseasSavedHsPayload) {
  return fetchApi<OverseasSavedHs & { success: boolean; updated?: boolean }>(
    `/overseas-shipping/saved-hs${overseasQuery(token)}`,
    { method: 'POST', body: JSON.stringify(payload) }
  );
}

export async function updateOverseasSavedHs(token: string, id: number, payload: OverseasSavedHsPayload) {
  return fetchApi<{ success: boolean; id: number; label: string }>(
    `/overseas-shipping/saved-hs/${id}${overseasQuery(token)}`,
    { method: 'PUT', body: JSON.stringify(payload) }
  );
}

export async function deleteOverseasSavedHs(token: string, id: number) {
  return fetchApi<{ success: boolean; id: number }>(
    `/overseas-shipping/saved-hs/${id}${overseasQuery(token)}`,
    { method: 'DELETE' }
  );
}

export async function searchOverseasItemCategories(token: string, q = '') {
  return fetchApi<{ items: Array<{ id: string; name_ko: string; name_en: string; hs_code: string; group: string }> }>(
    `/overseas-shipping/item-categories${overseasQuery(token, q ? `&q=${encodeURIComponent(q)}` : '')}`
  );
}
