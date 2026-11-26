import type { DayEntry, Worker } from './model';

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
