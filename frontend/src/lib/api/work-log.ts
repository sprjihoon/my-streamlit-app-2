import { API_BASE, fetchApi } from './client';

// ─────────────────────────────────────
// 작업일지 API
// ─────────────────────────────────────

export interface WorkLog {
  id: number;
  날짜: string | null;
  업체명: string | null;
  분류: string | null;
  단가: number | null;
  수량: number | null;
  합계: number | null;
  비고1: string | null;
  작성자: string | null;
  저장시간: string | null;
  출처: string | null;
  수정자: string | null;
  수정시간: string | null;
}

export interface WorkLogFilters {
  vendors: string[];
  work_types: string[];
  authors: string[];
  sources: string[];
}

export interface WorkLogResponse {
  logs: WorkLog[];
  total: number;
  filters: WorkLogFilters;
}

export interface WorkLogStats {
  total: number;
  total_amount: number;
  today: number;
  by_vendor: Array<{ 업체명: string; count: number; total_amount: number }>;
  by_work_type: Array<{ 분류: string; count: number; total_amount: number }>;
  by_source: Array<{ 출처: string; count: number }>;
}

/**
 * 작업일지 목록 조회
 */
export async function getWorkLogs(params?: {
  period_from?: string;
  period_to?: string;
  vendor?: string;
  work_type?: string;
  author?: string;
  source?: string;
  limit?: number;
  offset?: number;
}) {
  const queryParts: string[] = [];
  if (params?.period_from) queryParts.push(`period_from=${encodeURIComponent(params.period_from)}`);
  if (params?.period_to) queryParts.push(`period_to=${encodeURIComponent(params.period_to)}`);
  if (params?.vendor) queryParts.push(`vendor=${encodeURIComponent(params.vendor)}`);
  if (params?.work_type) queryParts.push(`work_type=${encodeURIComponent(params.work_type)}`);
  if (params?.author) queryParts.push(`author=${encodeURIComponent(params.author)}`);
  if (params?.source) queryParts.push(`source=${encodeURIComponent(params.source)}`);
  if (params?.limit) queryParts.push(`limit=${params.limit}`);
  if (params?.offset) queryParts.push(`offset=${params.offset}`);
  
  const query = queryParts.length > 0 ? `?${queryParts.join('&')}` : '';
  return fetchApi<WorkLogResponse>(`/work-log${query}`);
}

/**
 * 작업일지 통계 조회
 */
export async function getWorkLogStats(params?: {
  period_from?: string;
  period_to?: string;
}) {
  const queryParts: string[] = [];
  if (params?.period_from) queryParts.push(`period_from=${encodeURIComponent(params.period_from)}`);
  if (params?.period_to) queryParts.push(`period_to=${encodeURIComponent(params.period_to)}`);
  
  const query = queryParts.length > 0 ? `?${queryParts.join('&')}` : '';
  return fetchApi<WorkLogStats>(`/work-log/stats${query}`);
}

/**
 * 작업일지 상세 조회
 */
export async function getWorkLog(id: number) {
  return fetchApi<WorkLog>(`/work-log/${id}`);
}

/**
 * 작업일지 생성
 */
export async function createWorkLog(data: {
  날짜: string;
  업체명: string;
  분류: string;
  단가: number;
  수량?: number;
  비고1?: string;
  작성자?: string;
  출처?: string;
}) {
  return fetchApi<{ success: boolean; id: number; message: string }>('/work-log', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * 작업일지 수정
 */
export async function updateWorkLog(id: number, data: {
  날짜?: string;
  업체명?: string;
  분류?: string;
  단가?: number;
  수량?: number;
  비고1?: string;
}) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const q = token ? `?token=${encodeURIComponent(token)}` : '';
  return fetchApi<{ success: boolean; message: string }>(`/work-log/${id}${q}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

/**
 * 작업일지 삭제
 */
export async function deleteWorkLog(id: number) {
  return fetchApi<{ success: boolean; message: string }>(`/work-log/${id}`, {
    method: 'DELETE',
  });
}

export function getWorkLogExportUrl(
  startDate: string,
  endDate: string,
  vendor?: string,
  workType?: string,
  author?: string,
  source?: string,
) {
  const q = new URLSearchParams({ start_date: startDate, end_date: endDate });
  if (vendor) q.set('vendor', vendor);
  if (workType) q.set('work_type', workType);
  if (author) q.set('author', author);
  if (source) q.set('source', source);
  return `${API_BASE}/work-log/export?${q.toString()}`;
}
