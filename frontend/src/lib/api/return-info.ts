import { API_BASE, fetchApi } from './client';

export const RETURN_INFO_COLUMNS = [
  '상태',
  '등록일',
  '등록자',
  '입고일',
  '관리번호',
  '발주일',
  '판매처',
  '주문번호',
  '수령자',
  '상품명',
  '바코드',
  '옵션',
  '수량',
  '불량',
  'CS이력',
  '반품메모',
] as const;

export const RETURN_INFO_DATE_COLUMNS = ['등록일', '입고일', '발주일'] as const;

export type ReturnInfoColumn = (typeof RETURN_INFO_COLUMNS)[number];
export type ReturnInfoFilters = Record<string, string>;

export interface ReturnInfoList {
  columns: string[];
  rows: Array<Record<string, string | number | null>>;
  total: number;
  page: number;
  page_size: number;
}

function authToken() {
  return typeof window === 'undefined' ? null : localStorage.getItem('token');
}

export function returnInfoQuery(filters: ReturnInfoFilters, extra?: Record<string, string | number>) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value.trim()) params.set(key, value.trim());
  });
  if (extra) {
    Object.entries(extra).forEach(([key, value]) => params.set(key, String(value)));
  }
  const token = authToken();
  if (token) params.set('token', token);
  const query = params.toString();
  return query ? `?${query}` : '';
}

export interface ReturnInfoChoices {
  판매처: string[];
  상품명: string[];
}

export function getReturnInfoOptions() {
  return fetchApi<ReturnInfoChoices>(`/return-info/options${returnInfoQuery({})}`);
}

export function getReturnInfo(filters: ReturnInfoFilters, page: number, pageSize: number) {
  return fetchApi<ReturnInfoList>(
    `/return-info${returnInfoQuery(filters, { page, page_size: pageSize })}`,
  );
}

export async function downloadReturnInfoExcel(filters: ReturnInfoFilters) {
  const res = await fetch(`${API_BASE}/return-info/export${returnInfoQuery(filters)}`);
  if (!res.ok) {
    let detail = '엑셀 생성 실패';
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : detail;
    } catch {
      // 본문이 JSON이 아니면 기본 문구를 쓴다.
    }
    throw new Error(detail);
  }
  const buffer = await res.arrayBuffer();
  const blob = new Blob([buffer], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = 'return_info.xlsx';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(objectUrl);
}
