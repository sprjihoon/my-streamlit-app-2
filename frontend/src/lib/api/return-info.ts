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
  '공급처',
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

const MULTI_QUERY_KEYS = new Set(['판매처', '공급처']);

export function returnInfoQuery(filters: ReturnInfoFilters, extra?: Record<string, string | number>) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    const parts = MULTI_QUERY_KEYS.has(key)
      ? value.split('\n').map((part) => part.trim()).filter(Boolean)
      : [value.trim()].filter(Boolean);
    parts.forEach((part) => params.append(key, part));
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
  공급처: string[];
}

export function getReturnInfoOptions() {
  return fetchApi<ReturnInfoChoices>(`/return-info/options${returnInfoQuery({})}`);
}

export function getReturnInfo(filters: ReturnInfoFilters, page: number, pageSize: number) {
  return fetchApi<ReturnInfoList>(
    `/return-info${returnInfoQuery(filters, { page, page_size: pageSize })}`,
  );
}

function filenameFromDisposition(header: string | null, fallback: string) {
  if (!header) return fallback;
  const encoded = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1]);
    } catch {
      return fallback;
    }
  }
  const plain = header.match(/filename="?([^";]+)"?/i);
  return plain?.[1] || fallback;
}

async function downloadReturnInfoFile(path: string, filename: string | null, filters: ReturnInfoFilters, fallback: string) {
  const res = await fetch(`${API_BASE}${path}${returnInfoQuery(filters)}`);
  if (!res.ok) {
    let detail = fallback;
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
  link.download = filename || filenameFromDisposition(res.headers.get('Content-Disposition'), 'download.xlsx');
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(objectUrl);
}

export function downloadReturnInfoExcel(filters: ReturnInfoFilters) {
  return downloadReturnInfoFile('/return-info/export', 'return_info.xlsx', filters, '엑셀 생성 실패');
}

export function downloadReturnInfoReport(filters: ReturnInfoFilters) {
  return downloadReturnInfoFile('/return-info/report', null, filters, '보고서 생성 실패');
}
