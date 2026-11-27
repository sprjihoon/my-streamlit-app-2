import type { DayEntry, Worker } from './model';

export const DEFAULT_START = '09:00';

export function parseClockMinutes(value: string) {
  const text = (value || '').trim();
  const match = /^(\d{1,2}):(\d{2})/.exec(text);
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour > 23 || minute > 59) return null;
  return hour * 60 + minute;
}

export function shiftTimes(start: string, hours: number) {
  const startMinutes = parseClockMinutes(start);
  if (startMinutes === null) return null;
  const startHour = Math.floor(startMinutes / 60);
  const startMinute = startMinutes % 60;
  const startClock = `${String(startHour).padStart(2, '0')}:${String(startMinute).padStart(2, '0')}`;
  const extra = Math.max(0, Math.round(Number(hours || 0) * 60));
  const total = startMinutes + extra;
  const nextDay = total >= 24 * 60;
  const endMinutes = total % (24 * 60);
  const endClock = `${String(Math.floor(endMinutes / 60)).padStart(2, '0')}:${String(endMinutes % 60).padStart(2, '0')}`;
  return {
    startTime: startClock,
    endTime: endClock,
    nextDay,
    label: `${startClock}~${nextDay ? '익일 ' : ''}${endClock}`,
  };
}

export type DropOutcome =
  | { kind: 'hours'; workerId: number; name: string }
  | { kind: 'duplicate'; name: string }
  | { kind: 'ignore' };

export function workersAvailableOnDate(workers: Worker[], entries: DayEntry[]) {
  const taken = new Set(entries.map((item) => item.worker_id));
  return workers.filter((worker) => worker.active && !taken.has(worker.id));
}

export function dropWorkerOntoDate(workers: Worker[], entries: DayEntry[], workerId: number): DropOutcome {
  const worker = workers.find((item) => item.id === workerId);
  if (!worker || !worker.active) return { kind: 'ignore' };
  if (entries.some((item) => item.worker_id === workerId)) {
    return { kind: 'duplicate', name: worker.name };
  }
  return { kind: 'hours', workerId: worker.id, name: worker.name };
}

export function dateFromPointTarget(target: EventTarget | null) {
  if (!(target instanceof Element)) return null;
  const value = target.closest('[data-date]')?.getAttribute('data-date');
  return value || null;
}
