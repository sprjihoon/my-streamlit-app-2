import { API_BASE, fetchApi } from './client';

/**
 * 파일 업로드
 */
export async function uploadFile(file: File, table: string, token?: string) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('table', table);
  if (token) {
    formData.append('token', token);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/upload`, {
      method: 'POST',
      body: formData,
      // FormData를 사용할 때는 Content-Type을 설정하지 않아야 브라우저가 자동으로 boundary를 추가합니다
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (msg === 'Failed to fetch' || msg.includes('NetworkError') || msg.includes('Load failed')) {
      throw new Error('서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.');
    }
    throw e;
  }

  if (!response.ok) {
    let errorMessage = `Upload Error: ${response.status}`;
    try {
      const errorData = await response.json();
      errorMessage = errorData.detail || errorData.message || errorMessage;
    } catch {
      const errorText = await response.text();
      errorMessage = errorText || errorMessage;
    }
    throw new Error(errorMessage);
  }

  return response.json() as Promise<{
    success: boolean;
    message: string;
    filename?: string;
  }>;
}

/**
 * 업로드 목록 조회
 */
export async function getUploadList() {
  return fetchApi<{
    success: boolean;
    uploads: Array<{
      id: number;
      filename: string;
      원본명: string;
      table_name: string;
      시작일: string;
      종료일: string;
      업로드시각: string;
    }>;
  }>('/upload/list');
}

/**
 * 업로드 기록 삭제
 */
export async function deleteUpload(uploadId: number) {
  // localStorage에서 토큰 가져오기
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const queryParam = token ? `?token=${encodeURIComponent(token)}` : '';
  
  return fetchApi<{
    success: boolean;
    message: string;
  }>(`/upload/${uploadId}${queryParam}`, {
    method: 'DELETE',
  });
}

/**
 * 테이블 데이터 초기화
 */
export async function resetTableData(tableName: string) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const queryParam = token ? `?token=${encodeURIComponent(token)}` : '';
  
  return fetchApi<{
    success: boolean;
    message: string;
  }>(`/upload/table/${tableName}${queryParam}`, {
    method: 'DELETE',
  });
}

/**
 * 특정 기간 데이터만 삭제
 */
export async function resetTableDataByPeriod(
  tableName: string,
  dateFrom: string,
  dateTo: string,
) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
  if (token) params.set('token', token);

  return fetchApi<{
    success: boolean;
    message: string;
  }>(`/upload/table/${tableName}/period?${params.toString()}`, {
    method: 'DELETE',
  });
}
