/**
 * API 클라이언트
 * FastAPI 백엔드와 통신
 */

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/** 브라우저에서 사용할 API 베이스 URL (연결 확인용) */
export function getApiBase(): string {
  return API_BASE;
}

/**
 * API 요청 헬퍼
 * - 네트워크 실패 시 "Failed to fetch" 대신 안내 메시지 반환
 */
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;

  let response: Response;
  try {
    response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      ...options,
    });
  } catch (e) {
    const name = e instanceof Error ? e.name : '';
    if (name === 'AbortError' || (typeof DOMException !== 'undefined' && e instanceof DOMException && e.name === 'AbortError')) {
      throw e;
    }
    const msg = e instanceof Error ? e.message : String(e);
    if (msg === 'Failed to fetch' || msg.includes('NetworkError') || msg.includes('Load failed')) {
      throw new Error(
        `서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.`
      );
    }
    throw e;
  }

  if (!response.ok) {
    const error = await response.text();
    throw new ApiError(response.status, error || `API Error: ${response.status}`);
  }

  return response.json();
}

/**
 * 헬스체크
 */
export async function checkHealth() {
  return fetchApi<{ status: string; version: string }>('/health');
}
