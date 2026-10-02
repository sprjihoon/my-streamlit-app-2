import { fetchApi } from './client';

// ─────────────────────────────────────
// Logs API (관리자 전용)
// ─────────────────────────────────────

export interface ActivityLog {
  log_id: number;
  action_type: string;
  target_type: string | null;
  target_id: string | null;
  target_name: string | null;
  user_nickname: string | null;
  details: string | null;
  created_at: string | null;
}

export interface LogFilters {
  action_types: string[];
  target_types: string[];
  users: string[];
}

export interface LogsResponse {
  logs: ActivityLog[];
  total: number;
  filters: LogFilters;
}

export interface LogStats {
  total: number;
  today: number;
  by_action: Array<{ action_type: string; count: number }>;
  by_user: Array<{ user_nickname: string; count: number }>;
}

/**
 * 활동 로그 조회 (관리자만)
 */
export async function getLogs(token: string, params?: {
  period_from?: string;
  period_to?: string;
  action_type?: string;
  target_type?: string;
  user_nickname?: string;
  target_name?: string;
  limit?: number;
}) {
  const queryParts = [`token=${encodeURIComponent(token)}`];
  if (params?.period_from) queryParts.push(`period_from=${encodeURIComponent(params.period_from)}`);
  if (params?.period_to) queryParts.push(`period_to=${encodeURIComponent(params.period_to)}`);
  if (params?.action_type) queryParts.push(`action_type=${encodeURIComponent(params.action_type)}`);
  if (params?.target_type) queryParts.push(`target_type=${encodeURIComponent(params.target_type)}`);
  if (params?.user_nickname) queryParts.push(`user_nickname=${encodeURIComponent(params.user_nickname)}`);
  if (params?.target_name) queryParts.push(`target_name=${encodeURIComponent(params.target_name)}`);
  if (params?.limit) queryParts.push(`limit=${params.limit}`);
  
  const query = `?${queryParts.join('&')}`;
  return fetchApi<LogsResponse>(`/logs${query}`);
}

/**
 * 로그 통계 조회 (관리자만)
 */
export async function getLogStats(token: string) {
  return fetchApi<LogStats>(`/logs/stats?token=${encodeURIComponent(token)}`);
}
