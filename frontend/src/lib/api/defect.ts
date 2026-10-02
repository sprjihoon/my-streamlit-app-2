import { API_BASE, fetchApi } from './client';

// ─────────────────────────────────────
// 불량일지 API
// ─────────────────────────────────────

export interface DefectLog {
  id: number;
  날짜: string | null;
  업체명: string | null;
  제품명: string | null;
  옵션: string | null;
  바코드: string | null;
  불량명: string | null;
  수량: number | null;
  비고: string | null;
  작성자: string | null;
  저장시간: string | null;
  출처: string | null;
  before_image: string | null;
  after_image: string | null;
  extra_images?: string[] | null;
  처리결과: string | null;
  수정자: string | null;
  수정시간: string | null;
}

export interface DefectLogFilters {
  vendors: string[];
  defects: string[];
  authors: string[];
}

export interface DefectLogStats {
  total: number;
  today: number;
  unresolved: number;
  by_result: Array<{ 처리결과: string; count: number }>;
}

export function defectImageUrl(filename: string | null | undefined): string | null {
  if (!filename) return null;
  return `${API_BASE}/defect-log/image/${encodeURIComponent(filename)}`;
}

export async function getDefectLogs(params?: {
  period_from?: string;
  period_to?: string;
  vendor?: string;
  defect?: string;
  author?: string;
  result?: string;
  unresolved_only?: boolean;
  limit?: number;
  offset?: number;
}) {
  const q = new URLSearchParams();
  if (params?.period_from) q.set('period_from', params.period_from);
  if (params?.period_to) q.set('period_to', params.period_to);
  if (params?.vendor) q.set('vendor', params.vendor);
  if (params?.defect) q.set('defect', params.defect);
  if (params?.author) q.set('author', params.author);
  if (params?.result) q.set('result', params.result);
  if (params?.unresolved_only) q.set('unresolved_only', 'true');
  if (params?.limit != null) q.set('limit', String(params.limit));
  if (params?.offset != null) q.set('offset', String(params.offset));
  const qs = q.toString();
  return fetchApi<{ logs: DefectLog[]; total: number; filters: DefectLogFilters }>(
    `/defect-log${qs ? `?${qs}` : ''}`
  );
}

export async function getDefectLogStats(params?: {
  period_from?: string;
  period_to?: string;
}) {
  const q = new URLSearchParams();
  if (params?.period_from) q.set('period_from', params.period_from);
  if (params?.period_to) q.set('period_to', params.period_to);
  const qs = q.toString();
  return fetchApi<DefectLogStats>(`/defect-log/stats${qs ? `?${qs}` : ''}`);
}

export async function createDefectLog(data: {
  날짜: string;
  업체명?: string;
  제품명?: string;
  옵션?: string;
  바코드?: string;
  불량명?: string;
  수량?: number;
  비고?: string;
  작성자?: string;
  출처?: string;
  처리결과?: string;
}) {
  return fetchApi<{ success: boolean; id: number; message: string }>('/defect-log', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateDefectLog(id: number, data: Partial<{
  날짜: string;
  업체명: string;
  제품명: string;
  옵션: string;
  바코드: string;
  불량명: string;
  수량: number;
  비고: string;
  처리결과: string | null;
}>) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const q = token ? `?token=${encodeURIComponent(token)}` : '';
  return fetchApi<{ success: boolean; message: string }>(`/defect-log/${id}${q}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function updateDefectResult(id: number, 처리결과: string | null) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const q = token ? `?token=${encodeURIComponent(token)}` : '';
  return fetchApi<{ success: boolean; 처리결과: string | null; message: string }>(
    `/defect-log/${id}/result${q}`,
    { method: 'PATCH', body: JSON.stringify({ 처리결과 }) }
  );
}

export async function deleteDefectLog(id: number) {
  return fetchApi<{ success: boolean; message: string }>(`/defect-log/${id}`, {
    method: 'DELETE',
  });
}

export async function autoFillDefectFromBarcode(token?: string) {
  const qs = token ? `?token=${encodeURIComponent(token)}` : '';
  return fetchApi<{ updated: number; skipped: number; details: Array<{ id: number; barcode: string; result: string; 업체명?: string; 제품명?: string; 옵션?: string }> }>(
    `/defect-log/auto-fill-from-barcode${qs}`, { method: 'POST' }
  );
}

export async function uploadDefectPhotos(
  id: number,
  files: { before?: File | null; after?: File | null; extra?: File[] | null }
) {
  const form = new FormData();
  if (files.before) form.append('before', files.before);
  if (files.after) form.append('after', files.after);
  for (const file of files.extra || []) {
    form.append('extra', file);
  }
  const response = await fetch(`${API_BASE}/defect-log/${id}/photos`, { method: 'POST', body: form });
  if (!response.ok) {
    const err = await response.text();
    throw new Error(err || `Upload Error: ${response.status}`);
  }
  return response.json() as Promise<{ success: boolean; message: string }>;
}

export function getDefectLogExportUrl(
  startDate: string,
  endDate: string,
  vendor?: string,
  defect?: string,
  result?: string,
  author?: string,
) {
  const q = new URLSearchParams({ start_date: startDate, end_date: endDate });
  if (vendor) q.set('vendor', vendor);
  if (defect) q.set('defect', defect);
  if (result) q.set('result', result);
  if (author) q.set('author', author);
  return `${API_BASE}/defect-log/export?${q.toString()}`;
}
