import { API_BASE, fetchApi } from './client';

// ─────────────────────────────────────
// 수선작업일지
// ─────────────────────────────────────

export interface RepairLog {
  id: number;
  날짜: string | null;
  업체명: string | null;
  제품명: string | null;
  옵션: string | null;
  바코드: string | null;
  불량명: string | null;
  작업: string | null;
  수량: number | null;
  비용: number | null;
  비고: string | null;
  작성자: string | null;
  저장시간: string | null;
  출처: string | null;
  수정자: string | null;
  수정시간: string | null;
  barcode_image: string | null;
  before_image: string | null;
  after_image: string | null;
  extra_images?: string[] | null;
}

export interface RepairLogFilters {
  vendors: string[];
  work_types: string[];
  defects: string[];
  authors: string[];
}

export interface RepairWorkType {
  작업명: string;
  기본비용: number;
  별칭: string | null;
}

export interface RepairDefect {
  불량명: string;
  별칭: string | null;
}

export interface RepairLogStats {
  total: number;
  total_amount: number;
  today: number;
  by_source: Array<{ 출처: string; count: number }>;
}

export interface RepairBarcode {
  바코드: string;
  업체명: string;
  제품명: string;
  옵션: string | null;
  도매처: string | null;
  도매처주소: string | null;
  도매처연락처: string | null;
  상품코드: string | null;
  로케이션: string | null;
  상품명: string | null;
  출처: string | null;
  저장시간: string | null;
}

export function repairImageUrl(filename: string | null | undefined): string | null {
  if (!filename) return null;
  return `${API_BASE}/repair-log/image/${encodeURIComponent(filename)}`;
}

export async function getRepairLogs(params?: {
  period_from?: string;
  period_to?: string;
  vendor?: string;
  work_type?: string;
  defect?: string;
  author?: string;
  limit?: number;
  offset?: number;
}) {
  const q = new URLSearchParams();
  if (params?.period_from) q.set('period_from', params.period_from);
  if (params?.period_to) q.set('period_to', params.period_to);
  if (params?.vendor) q.set('vendor', params.vendor);
  if (params?.work_type) q.set('work_type', params.work_type);
  if (params?.defect) q.set('defect', params.defect);
  if (params?.author) q.set('author', params.author);
  if (params?.limit != null) q.set('limit', String(params.limit));
  if (params?.offset != null) q.set('offset', String(params.offset));
  const qs = q.toString();
  return fetchApi<{ logs: RepairLog[]; total: number; filters: RepairLogFilters }>(
    `/repair-log${qs ? `?${qs}` : ''}`
  );
}

function repairLogFilterQuery(params?: {
  period_from?: string;
  period_to?: string;
  vendor?: string;
  work_type?: string;
  defect?: string;
  author?: string;
}) {
  const q = new URLSearchParams();
  if (params?.period_from) q.set('period_from', params.period_from);
  if (params?.period_to) q.set('period_to', params.period_to);
  if (params?.vendor) q.set('vendor', params.vendor);
  if (params?.work_type) q.set('work_type', params.work_type);
  if (params?.defect) q.set('defect', params.defect);
  if (params?.author) q.set('author', params.author);
  return q;
}

export async function getRepairLogStats(params?: {
  period_from?: string;
  period_to?: string;
  vendor?: string;
  work_type?: string;
  defect?: string;
  author?: string;
}) {
  const qs = repairLogFilterQuery(params).toString();
  return fetchApi<RepairLogStats>(`/repair-log/stats${qs ? `?${qs}` : ''}`);
}

export async function createRepairLog(data: {
  날짜: string;
  업체명?: string;
  제품명?: string;
  옵션?: string;
  바코드?: string;
  불량명?: string;
  작업: string;
  수량?: number;
  비용: number;
  비고?: string;
  작성자?: string;
  출처?: string;
}) {
  return fetchApi<{ success: boolean; id: number; message: string }>('/repair-log', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateRepairLog(id: number, data: Partial<{
  날짜: string;
  업체명: string;
  제품명: string;
  옵션: string;
  바코드: string;
  불량명: string;
  작업: string;
  수량: number;
  비용: number;
  비고: string;
}>) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const q = token ? `?token=${encodeURIComponent(token)}` : '';
  return fetchApi<{ success: boolean; message: string }>(`/repair-log/${id}${q}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteRepairLog(id: number) {
  return fetchApi<{ success: boolean; message: string }>(`/repair-log/${id}`, {
    method: 'DELETE',
  });
}

export async function uploadRepairPhotos(
  id: number,
  files: { before?: File | null; after?: File | null; barcode?: File | null; extra?: File[] | null }
) {
  const form = new FormData();
  if (files.before) form.append('before', files.before);
  if (files.after) form.append('after', files.after);
  if (files.barcode) form.append('barcode', files.barcode);
  for (const file of files.extra || []) {
    form.append('extra', file);
  }
  const response = await fetch(`${API_BASE}/repair-log/${id}/photos`, { method: 'POST', body: form });
  if (!response.ok) {
    const err = await response.text();
    throw new Error(err || `Upload Error: ${response.status}`);
  }
  return response.json() as Promise<{ success: boolean; message: string }>;
}

export function getRepairLogExportUrl(
  startDate: string,
  endDate: string,
  vendor?: string,
  workType?: string,
  defect?: string,
  author?: string,
) {
  const q = new URLSearchParams({ start_date: startDate, end_date: endDate });
  if (vendor) q.set('vendor', vendor);
  if (workType) q.set('work_type', workType);
  if (defect) q.set('defect', defect);
  if (author) q.set('author', author);
  return `${API_BASE}/repair-log/export?${q.toString()}`;
}

export async function getOldRepairPhotos(days = 60) {
  return fetchApi<{ cutoff: string; days: number; logs: number; files: number }>(
    `/repair-log/photos/old?days=${days}`
  );
}

export async function purgeOldRepairPhotos(days = 60) {
  return fetchApi<{ success: boolean; cutoff: string; logs: number; deleted_files: number; message: string }>(
    `/repair-log/photos/purge-old?days=${days}`,
    { method: 'POST' }
  );
}

export async function getRepairBarcodes(params?: {
  q?: string;
  vendor?: string;
  limit?: number;
  offset?: number;
}) {
  const query = new URLSearchParams();
  if (params?.q) query.set('q', params.q);
  if (params?.vendor) query.set('vendor', params.vendor);
  if (params?.limit != null) query.set('limit', String(params.limit));
  if (params?.offset != null) query.set('offset', String(params.offset));
  const qs = query.toString();
  return fetchApi<{
    items: RepairBarcode[];
    total: number;
    filters: { vendors: string[] };
  }>(`/repair-log/barcodes${qs ? `?${qs}` : ''}`);
}

export async function lookupRepairBarcode(barcode: string) {
  return fetchApi<RepairBarcode>(`/repair-log/barcodes/lookup/${encodeURIComponent(barcode)}`);
}

export async function createRepairBarcode(data: {
  바코드: string;
  업체명: string;
  제품명: string;
  옵션?: string;
  도매처?: string;
  상품코드?: string;
  로케이션?: string;
  상품명?: string;
}) {
  return fetchApi<{ success: boolean; message: string }>('/repair-log/barcodes', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateRepairBarcode(barcode: string, data: Partial<{
  업체명: string;
  제품명: string;
  옵션: string;
  도매처: string;
  상품코드: string;
  로케이션: string;
  상품명: string;
}>) {
  return fetchApi<{ success: boolean; message: string }>(
    `/repair-log/barcodes/${encodeURIComponent(barcode)}`,
    { method: 'PUT', body: JSON.stringify(data) }
  );
}

export async function deleteRepairBarcode(barcode: string) {
  return fetchApi<{ success: boolean; message: string }>(
    `/repair-log/barcodes/${encodeURIComponent(barcode)}`,
    { method: 'DELETE' }
  );
}

export async function uploadRepairBarcodes(file: File) {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch(`${API_BASE}/repair-log/barcodes/upload`, { method: 'POST', body: form });
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
  return response.json() as Promise<{
    success: boolean;
    inserted: number;
    updated: number;
    total: number;
    message: string;
  }>;
}

export function getRepairBarcodeTemplateUrl() {
  return `${API_BASE}/repair-log/barcodes/template`;
}

export async function getRepairCatalog() {
  return fetchApi<{ work_types: RepairWorkType[]; defects: RepairDefect[] }>('/repair-log/catalog');
}

export async function getRepairCatalogPrice(workType: string, vendor?: string, product?: string) {
  const q = new URLSearchParams({ work_type: workType });
  if (vendor) q.set('vendor', vendor);
  if (product) q.set('product', product);
  return fetchApi<{
    found: boolean;
    source: string | null;
    작업명: string;
    비용: number | null;
    기본비용: number | null;
    message: string;
  }>(`/repair-log/catalog/price?${q.toString()}`);
}

export async function saveRepairWorkType(data: { 작업명: string; 기본비용: number; 별칭?: string }) {
  return fetchApi<{ success: boolean; message: string }>('/repair-log/catalog/work-types', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function deleteRepairWorkType(name: string) {
  return fetchApi<{ success: boolean; message: string }>(
    `/repair-log/catalog/work-types/${encodeURIComponent(name)}`,
    { method: 'DELETE' }
  );
}

export async function saveRepairDefect(data: { 불량명: string; 별칭?: string }) {
  return fetchApi<{ success: boolean; message: string }>('/repair-log/catalog/defects', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function deleteRepairDefect(name: string) {
  return fetchApi<{ success: boolean; message: string }>(
    `/repair-log/catalog/defects/${encodeURIComponent(name)}`,
    { method: 'DELETE' }
  );
}
