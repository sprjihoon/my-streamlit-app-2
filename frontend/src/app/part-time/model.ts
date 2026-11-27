export const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface Worker {
  id: number;
  name: string;
  resident_id: string;
  reported: boolean;
  hourly_wage: number;
  active: boolean;
}

export interface DayEntry {
  worker_id: number;
  name: string;
  hours: number;
  start_time?: string;
  end_time?: string;
  next_day?: boolean;
  shift_label?: string;
  reported: boolean;
  hourly_wage: number;
  pay: number;
}

export interface WeekPerson {
  worker_id: number;
  name: string;
  reported: boolean;
  basic_hours: number;
  weekly_holiday_hours: number;
  weekly_holiday_pay: number;
}

export interface PersonTotal {
  worker_id: number;
  name: string;
  reported: boolean;
  hourly_wage: number;
  active: boolean;
  basic_hours: number;
  base_pay: number;
  weekly_holiday_hours: number;
  weekly_holiday_pay: number;
  total_pay: number;
}

export interface CalendarData {
  year: number;
  month: number;
  minimum_wage: number;
  workers: Worker[];
  days: Record<string, DayEntry[]>;
  weeks: { monday: string; sunday: string; workers: WeekPerson[] }[];
  totals: PersonTotal[];
}

export function won(value: number) {
  return `${Math.round(value).toLocaleString('ko-KR')}원`;
}

export function hoursText(value: number) {
  const rounded = Math.round(value * 100) / 100;
  return Number.isInteger(rounded) ? String(rounded) : String(rounded);
}

export async function apiError(res: Response) {
  try {
    const data = await res.json();
    return data.detail || '요청을 처리하지 못했습니다.';
  } catch {
    return '요청을 처리하지 못했습니다.';
  }
}

export async function downloadPartTimeExcel(year: number, month: number) {
  const token = localStorage.getItem('token') || '';
  const res = await fetch(`${API}/part-time/xlsx?token=${encodeURIComponent(token)}&year=${year}&month=${month}`);
  if (!res.ok) throw new Error(await apiError(res));
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `틸리언 일용근로대장 ${year}년 ${String(month).padStart(2, '0')}월.xlsx`;
  link.click();
  URL.revokeObjectURL(url);
}

export function readAdmin() {
  try {
    return !!JSON.parse(localStorage.getItem('user') || '{}').is_admin;
  } catch {
    return false;
  }
}
