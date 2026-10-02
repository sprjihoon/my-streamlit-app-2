import { API_BASE, fetchApi } from './client';

// ─────────────────────────────────────────────────────────────────
// 입고모드 (Inbound)
// ─────────────────────────────────────────────────────────────────

export interface InboundBatch {
  id: string;
  vendor: string;
  inbound_date: string;
  status: string;
  status_label: string;
  memo: string | null;
  receipt_id: string | null;
  janggi_filename: string | null;
  janggi_date: string | null;
  janggi_no: string | null;
  wholesale: string | null;
  total_janggi_qty: number;
  total_actual_qty: number;
  total_missing_qty: number;
  created_by: string | null;
  closed_by: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  items?: InboundItem[];
}

export interface InboundItem {
  id: string;
  batch_id: string;
  line_no: number;
  confirmed_by: string | null;
  item_wholesale: string | null;
  item_name: string | null;
  option_text: string | null;
  unit_price: number | null;
  janggi_qty: number;
  actual_qty: number;
  missing_qty: number;
  status: string;
  status_label: string;
  matched_barcode: string | null;
  matched_vendor: string | null;
  matched_product: string | null;
  matched_option: string | null;
  match_confidence: number;
  needs_matching: boolean;
  memo: string | null;
  supplier_location: string | null;
  supplier_contact: string | null;
  created_at: string;
  updated_at: string | null;
  actual_qty_confirmed: boolean;
  photo_decision: 'photo' | 'existing' | 'new' | 'none' | null;
  photos?: InboundItemPhoto[];
}

export interface InboundItemPhoto {
  id: string;
  url: string;
  filename: string;
  created_at: string;
}

export interface InboundInboxPhoto {
  id: string;
  sha256: string;
  filename: string | null;
  stored_filename: string | null;  // 실제 저장 파일명 (inbound_item_photos.filename 과 비교용)
  url: string | null;
  item_id: string | null;
  matched: boolean;
  created_at: string;
}

function inboundHeaders(token: string) {
  return { Authorization: `Bearer ${token}` };
}

export async function listInboundBatches(
  token: string,
  filters?: { vendor?: string; wholesale?: string; status?: string; dateFrom?: string; dateTo?: string; limit?: number; offset?: number }
) {
  const params = new URLSearchParams();
  if (filters?.vendor) params.set('vendor', filters.vendor);
  if (filters?.wholesale) params.set('wholesale', filters.wholesale);
  if (filters?.status) params.set('status', filters.status);
  if (filters?.dateFrom) params.set('date_from', filters.dateFrom);
  if (filters?.dateTo) params.set('date_to', filters.dateTo);
  if (filters?.limit != null) params.set('limit', String(filters.limit));
  if (filters?.offset != null) params.set('offset', String(filters.offset));
  const qs = params.toString() ? `?${params.toString()}` : '';
  return fetchApi<{ items: InboundBatch[]; total: number }>(
    `/inbound/batches${qs}`,
    { headers: inboundHeaders(token) }
  );
}

export async function createInboundBatch(token: string, body: { vendor: string; vendor_canonical?: string; inbound_date: string; memo?: string }) {
  return fetchApi<{ id: string; status: string }>(
    '/inbound/batches',
    { method: 'POST', headers: { ...inboundHeaders(token), 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
  );
}

export async function getInboundBatch(token: string, batchId: string) {
  // 실수량 입력 링크는 토큰 없이도 접근 가능
  const opts: RequestInit = token ? { headers: inboundHeaders(token) } : {};
  return fetchApi<InboundBatch>(`/inbound/batches/${batchId}`, opts);
}

export async function updateInboundBatch(token: string, batchId: string, body: { status?: string; memo?: string; vendor?: string; inbound_date?: string }) {
  return fetchApi<{ ok: boolean }>(
    `/inbound/batches/${batchId}`,
    { method: 'PATCH', headers: { ...inboundHeaders(token), 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
  );
}

export interface OcrPreviewReceipt {
  storeName: string | null;
  receiptNo: string | null;
  orderDate: string | null;
  totalAmount: number | null;
  isHandwritten: boolean;
  confidence: number;
  needsReview: boolean;
  warnings: string[];
}
export interface OcrPreviewItem {
  lineNo: number;
  itemName: string;
  color: string | null;
  optionText: string | null;
  unitPrice: number | null;
  quantity: number | null;
  amount: number | null;
  confidence: number;
  needsReview: boolean;
  warnings: string[];
}
/** 이미지를 maxPx 이하로 리사이즈 후 JPEG 압축 (OCR 속도 개선용) */
async function compressImageForOcr(file: File, maxPx = 2048, quality = 0.90): Promise<File> {
  return new Promise((resolve) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(url);
      const { width, height } = img;
      const scale = Math.min(1, maxPx / Math.max(width, height));
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(width * scale);
      canvas.height = Math.round(height * scale);
      const ctx = canvas.getContext('2d')!;
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(
        (blob) => resolve(blob ? new File([blob], file.name.replace(/\.[^.]+$/, '.jpg'), { type: 'image/jpeg' }) : file),
        'image/jpeg', quality
      );
    };
    img.onerror = () => { URL.revokeObjectURL(url); resolve(file); };
    img.src = url;
  });
}

export async function ocrPreview(token: string, file: File) {
  const compressed = await compressImageForOcr(file);
  const form = new FormData();
  form.append('file', compressed);
  // 프록시 경유 (브라우저 → Vercel → Railway) → 장거리 TCP 유지 문제 해결
  const response = await fetch('/api/ocr/preview', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (!response.ok) {
    const err = await response.text().catch(() => '');
    throw new Error(err || `OCR 실패 (${response.status})`);
  }
  return response.json() as Promise<{ ok: boolean; receipt: OcrPreviewReceipt; items: OcrPreviewItem[]; raw: unknown }>;
}

export async function runInboundOcr(token: string, batchId: string, file: File) {
  const compressed = await compressImageForOcr(file);
  const form = new FormData();
  form.append('file', compressed);
  // 프록시 경유 (브라우저 → Vercel → Railway) → 장거리 TCP 유지 문제 해결
  const response = await fetch(`/api/ocr/batch/${encodeURIComponent(batchId)}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (!response.ok) {
    const err = await response.text().catch(() => '');
    throw new Error(err || `OCR 실패 (${response.status})`);
  }
  return response.json() as Promise<{ ok: boolean; item_count: number; matched_count: number; needs_matching_count: number; wholesale: string | null; items: InboundItem[] }>;
}

export async function addInboundItem(token: string, batchId: string, body: {
  item_name: string;
  option_text?: string;
  janggi_qty: number;
  unit_price?: number;
  memo?: string;
  matched_barcode?: string;
  matched_vendor?: string;
  matched_product?: string;
  matched_option?: string;
  supplier_location?: string;
  supplier_contact?: string;
}) {
  return fetchApi<{ id: string }>(
    `/inbound/batches/${batchId}/items`,
    { method: 'POST', headers: { ...inboundHeaders(token), 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
  );
}

export async function deleteInboundItem(token: string, itemId: string) {
  return fetchApi<{ ok: boolean }>(
    `/inbound/items/${itemId}`,
    { method: 'DELETE', headers: inboundHeaders(token) }
  );
}

export async function updateInboundItem(token: string, itemId: string, body: Partial<{
  actual_qty: number; missing_qty: number; status: string; memo: string;
  item_name: string; option_text: string; item_wholesale: string;
  matched_barcode: string; matched_vendor: string; matched_product: string; matched_option: string;
  supplier_location: string; supplier_contact: string;
  confirmed_by: string;
  photo_decision: 'photo' | 'existing' | 'new' | 'none';
}>) {
  return fetchApi<{ ok: boolean }>(
    `/inbound/items/${itemId}`,
    { method: 'PATCH', headers: { ...inboundHeaders(token), 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
  );
}

export async function gradeCompleteInboundBatch(token: string, batchId: string) {
  return fetchApi<{ ok: boolean; moved: number; message: string }>(
    `/inbound/batches/${batchId}/grade-complete`,
    { method: 'POST', headers: { ...inboundHeaders(token), 'Content-Type': 'application/json' } }
  );
}

export async function closeInboundBatch(
  token: string,
  batchId: string,
  closeType: 'am' | 'pm' = 'am',
) {
  return fetchApi<{
    ok: boolean;
    close_type?: 'am' | 'pm';
    status?: string;
    status_label?: string;
    message?: string;
    warning?: string;
    defect_count?: number;
    defect_qty?: number;
    repair_qty?: number;
    zero_qty_count?: number;
    graded_count?: number;
    unconfirmed_count?: number;
    unconfirmed_items?: { id: string; line_no: number; item_name: string; janggi_qty: number }[];
    undecided_photo_count?: number;
    undecided_photo_items?: { id: string; line_no: number; item_name: string; actual_qty: number }[];
    // PM 마감 시 수량 정산
    total_janggi_qty?: number;
    '정상_qty'?: number;
    '수선중_qty'?: number;
    '수선후정상_qty'?: number;
    '회생불가_qty'?: number;
    '미입고_qty'?: number;
    formula_total?: number;
    discrepancy?: number;
    formula_ok?: boolean;
    formula_str?: string;
  }>(
    `/inbound/batches/${batchId}/close`,
    {
      method: 'POST',
      headers: { ...inboundHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ close_type: closeType }),
    }
  );
}

export async function deleteInboundBatch(token: string, batchId: string) {
  return fetchApi<{ ok: boolean }>(`/inbound/batches/${batchId}`, { method: 'DELETE', headers: inboundHeaders(token) });
}

export interface InboundRegisteredVendor {
  name: string;
  aliases: string[];
}

export interface VendorAlias {
  canonical: string;
  aliases: string[];
  memo: string | null;
}

export async function listInboundVendors(token: string) {
  return fetchApi<{ registered: InboundRegisteredVendor[]; recent: string[] }>(
    '/inbound/vendors', { headers: inboundHeaders(token) }
  );
}

export interface InboundAliasGroup {
  canonical: string;
  aliases: string[];
}

export async function getInboundFilterOptions(token: string) {
  return fetchApi<{ vendors: string[]; wholesales: string[]; alias_groups: InboundAliasGroup[] }>(
    '/inbound/filter-options', { headers: inboundHeaders(token) }
  );
}

export async function getVendorAliases(token: string) {
  return fetchApi<{ aliases: VendorAlias[] }>('/inbound/vendor-aliases', { headers: inboundHeaders(token) });
}

export async function upsertVendorAlias(token: string, canonical: string, aliases: string[], memo?: string) {
  return fetchApi<{ ok: boolean; canonical: string; aliases: string[] }>(
    `/inbound/vendor-aliases/${encodeURIComponent(canonical)}`,
    { method: 'PUT', headers: { ...inboundHeaders(token), 'Content-Type': 'application/json' }, body: JSON.stringify({ aliases, memo }) }
  );
}

export async function deleteVendorAlias(token: string, canonical: string) {
  return fetchApi<{ ok: boolean }>(`/inbound/vendor-aliases/${encodeURIComponent(canonical)}`, { method: 'DELETE', headers: inboundHeaders(token) });
}

export async function listInboundInboxPhotos(token: string, batchId: string) {
  return fetchApi<{ batch_id: string; photos: InboundInboxPhoto[]; total: number; unmatched: number }>(
    `/inbound/batches/${batchId}/inbox`,
    { headers: inboundHeaders(token) }
  );
}

/** 봇 inbox 사진을 품목에 연결 (파일 복사 없음) */
export async function linkInboxPhotoToItem(
  token: string,
  itemId: string,
  inboxPhotoId: string
) {
  return fetchApi<{ ok: boolean; id: string; url: string; duplicated: boolean }>(
    `/inbound/items/${itemId}/photos/from-inbox`,
    {
      method: 'POST',
      headers: { ...inboundHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ inbox_photo_id: inboxPhotoId }),
    }
  );
}

export async function unlinkInboxPhotoFromItem(token: string, itemId: string, inboxPhotoId: string) {
  return fetchApi<{ ok: boolean; unlinked: boolean; inbox_photo_id: string; item_id: string }>(
    `/inbound/items/${itemId}/photos/from-inbox/${inboxPhotoId}`,
    { method: 'DELETE', headers: inboundHeaders(token) }
  );
}

export async function downloadInboundBarcodePdf(token: string, batchId: string, vendor: string, date: string) {
  const res = await fetch(`${API_BASE}/inbound/batches/${batchId}/barcode-pdf`, {
    method: 'POST',
    headers: inboundHeaders(token),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `PDF 생성 실패: ${res.status}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `barcode_${vendor}_${date}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}
