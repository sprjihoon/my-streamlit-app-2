/**
 * 타입 정의
 * FastAPI 백엔드 스키마와 동일한 구조
 */

// 인보이스 항목
export interface InvoiceItem {
  항목: string;
  수량: number;
  단가: number;
  금액: number;
  비고?: string;
}

// 인보이스 계산 요청
export interface InvoiceCalculateRequest {
  vendor: string;
  date_from: string;
  date_to: string;
  include_basic_shipping?: boolean;
  include_courier_fee?: boolean;
  include_inbound_fee?: boolean;
  include_remote_fee?: boolean;
  include_worklog?: boolean;
}

// 인보이스 계산 응답
export interface InvoiceCalculateResponse {
  success: boolean;
  vendor: string;
  date_from: string;
  date_to: string;
  items: InvoiceItem[];
  total_amount: number;
  warnings: string[];
}

// 택배요금 응답
export interface CourierFeeResponse {
  success: boolean;
  vendor: string;
  zone_counts: Record<string, number>;
  items: InvoiceItem[];
}

// 배송통계 응답
export interface ShippingStatsResponse {
  success: boolean;
  vendor: string;
  count: number;
  data: Record<string, unknown>[];
}

// 업로드 응답
export interface UploadResponse {
  success: boolean;
  message: string;
  filename?: string;
}

// 업로드 목록 응답
export interface UploadListResponse {
  success: boolean;
  uploads: UploadRecord[];
}

export interface UploadRecord {
  id: number;
  filename: string;
  원본명: string;
  table_name: string;
  시작일: string;
  종료일: string;
  업로드시각: string;
}

// 헬스체크 응답
export interface HealthResponse {
  status: string;
  version: string;
}

