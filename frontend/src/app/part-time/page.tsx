'use client';

import { useCallback, useEffect, useState } from 'react';
import { Alert } from '@/components/Alert';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import { useYesNo } from '@/components/YesNoDialog';
import PageHeader from '@/components/ui/page-header';
import { Button } from '@/components/ui/button';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Worker {
  id: number;
  name: string;
  resident_id: string;
  reported: boolean;
  hourly_wage: number;
  active: boolean;
}

interface DayEntry {
  worker_id: number;
  name: string;
  hours: number;
  reported: boolean;
}

interface WeekPerson {
  worker_id: number;
  name: string;
  reported: boolean;
  basic_hours: number;
  weekly_holiday_hours: number;
  weekly_holiday_pay: number;
}

interface CalendarData {
  year: number;
  month: number;
  minimum_wage: number;
  workers: Worker[];
  days: Record<string, DayEntry[]>;
  weeks: { monday: string; sunday: string; workers: WeekPerson[] }[];
  totals: {
    worker_id: number;
    name: string;
    reported: boolean;
    hourly_wage: number;
    basic_hours: number;
    weekly_holiday_hours: number;
    weekly_holiday_pay: number;
  }[];
}

const WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일'];

function won(value: number) {
  return `${Math.round(value).toLocaleString('ko-KR')}원`;
}

function hoursText(value: number) {
  const rounded = Math.round(value * 100) / 100;
  return Number.isInteger(rounded) ? String(rounded) : String(rounded);
}

async function apiError(res: Response) {
  try {
    const data = await res.json();
    return data.detail || '요청을 처리하지 못했습니다.';
  } catch {
    return '요청을 처리하지 못했습니다.';
  }
}

export default function PartTimePage() {
  const { ask, dialog } = useYesNo();
  const now = new Date();
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [calendar, setCalendar] = useState<CalendarData | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [name, setName] = useState('');
  const [residentId, setResidentId] = useState('');
  const [reported, setReported] = useState(true);
  const [wage, setWage] = useState('');
  const [wageTouched, setWageTouched] = useState(false);
  const [edits, setEdits] = useState<Record<number, { name: string; reported: boolean; hourly_wage: string; resident_id: string }>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const fillDrafts = useCallback((data: CalendarData, date: string | null) => {
    if (!date) return;
    const next: Record<number, string> = {};
    const present = new Set((data.days[date] || []).map((item) => item.worker_id));
    data.workers.forEach((worker) => {
      if (worker.active || present.has(worker.id)) next[worker.id] = '';
    });
    (data.days[date] || []).forEach((item) => {
      next[item.worker_id] = hoursText(item.hours);
    });
    setDrafts(next);
  }, []);

  const load = useCallback(async (nextYear: number, nextMonth: number, date: string | null) => {
    const token = localStorage.getItem('token') || '';
    setLoading(true);
    setError(null);
    const res = await fetch(`${API}/part-time/calendar?token=${encodeURIComponent(token)}&year=${nextYear}&month=${nextMonth}`);
    setLoading(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    const data: CalendarData = await res.json();
    setCalendar(data);
    setEdits((current) => {
      const next = { ...current };
      data.workers.forEach((worker) => {
        if (!next[worker.id]) {
          next[worker.id] = { name: worker.name, reported: worker.reported, hourly_wage: String(worker.hourly_wage), resident_id: '' };
        }
      });
      return next;
    });
    fillDrafts(data, date);
  }, [fillDrafts]);

  useEffect(() => {
    let admin = false;
    try {
      admin = !!JSON.parse(localStorage.getItem('user') || '{}').is_admin;
    } catch {
      admin = false;
    }
    setIsAdmin(admin);
    if (admin) load(year, month, selected);
    else setLoading(false);
  }, [load, year, month]); // selected is applied inside load via the argument captured at call time

  useEffect(() => {
    if (!calendar) return;
    if (!wageTouched) setWage(String(calendar.minimum_wage));
  }, [calendar, wageTouched]);

  function shiftMonth(delta: number) {
    const next = new Date(year, month - 1 + delta, 1);
    setSelected(null);
    setYear(next.getFullYear());
    setMonth(next.getMonth() + 1);
  }

  function chooseDay(date: string) {
    setSelected(date);
    if (calendar) fillDrafts(calendar, date);
  }

  async function register() {
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    setSuccess(null);
    const res = await fetch(`${API}/part-time/workers?token=${encodeURIComponent(token)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        resident_id: residentId,
        reported,
        hourly_wage: Number(wage || 0),
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    setName('');
    setResidentId('');
    setReported(true);
    setWageTouched(false);
    setSuccess('알바를 등록했습니다.');
    await load(year, month, selected);
  }

  async function saveWorker(worker: Worker) {
    const edit = edits[worker.id];
    if (!edit) return;
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    setSuccess(null);
    const body: Record<string, string | number | boolean> = {
      name: edit.name,
      reported: edit.reported,
      hourly_wage: Number(edit.hourly_wage || 0),
    };
    if (edit.resident_id.trim()) body.resident_id = edit.resident_id.trim();
    const res = await fetch(`${API}/part-time/workers/${worker.id}?token=${encodeURIComponent(token)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    setEdits((current) => ({ ...current, [worker.id]: { ...edit, resident_id: '' } }));
    setSuccess(`${edit.name} 정보를 저장했습니다.`);
    await load(year, month, selected);
  }

  async function setActive(worker: Worker, active: boolean) {
    if (!active) {
      const ok = await ask(`${worker.name} 알바를 그만둔 사람으로 둡니다.\n지난 근무 기록은 달력에 남습니다.\n진행할까요?`);
      if (!ok) return;
    }
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    const res = await fetch(`${API}/part-time/workers/${worker.id}?token=${encodeURIComponent(token)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    await load(year, month, selected);
  }

  async function saveDay() {
    if (!selected || !calendar) return;
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    setSuccess(null);
    const entries = Object.entries(drafts).map(([workerId, value]) => ({
      worker_id: Number(workerId),
      hours: Number(value || 0),
    }));
    const res = await fetch(`${API}/part-time/days?token=${encodeURIComponent(token)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ work_date: selected, entries }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    const data: CalendarData = await res.json();
    setCalendar(data);
    fillDrafts(data, selected);
    setSuccess(`${selected} 근무시간을 기록했습니다.`);
  }

  if (isAdmin === null) return <Loading text="불러오는 중..." />;
  if (!isAdmin) {
    return (
      <div>
        <PageHeader title="관리대장" subtitle="아르바이트" />
        <Alert type="error" message="관리자만 아르바이트 관리대장을 볼 수 있습니다." />
      </div>
    );
  }

  const minimum = calendar?.minimum_wage || 0;
  const first = new Date(year, month - 1, 1);
  const daysInMonth = new Date(year, month, 0).getDate();
  const leading = (first.getDay() + 6) % 7;
  const cells: (number | null)[] = [...Array(leading).fill(null), ...Array.from({ length: daysInMonth }, (_, index) => index + 1)];
  while (cells.length % 7 !== 0) cells.push(null);
  const today = new Date();
  const holidayBySunday = new Map((calendar?.weeks || []).map((week) => [week.sunday, week.workers.filter((person) => person.weekly_holiday_pay > 0)]));

  return (
    <div>
      {dialog}
      <PageHeader
        title="관리대장"
        subtitle="알바를 등록하고 달력에 실제 근무시간을 적습니다. 신고 알바만 주휴수당이 계산됩니다."
      />
      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}
      {success && <Alert type="success" message={success} onClose={() => setSuccess(null)} />}

      <Card title="알바 등록" style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'end' }}>
          <label className="ops-label">
            이름
            <input className="ui-control" value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label className="ops-label">
            주민번호
            <input className="ui-control" value={residentId} placeholder="900101-1234567" onChange={(event) => setResidentId(event.target.value)} />
          </label>
          <label className="ops-label">
            구분
            <select className="ui-control" value={reported ? 'reported' : 'unreported'} onChange={(event) => setReported(event.target.value === 'reported')}>
              <option value="reported">신고</option>
              <option value="unreported">미신고</option>
            </select>
          </label>
          <label className="ops-label">
            시급
            <input
              className="ui-control"
              type="number"
              min={1}
              value={wage}
              onChange={(event) => {
                setWageTouched(true);
                setWage(event.target.value);
              }}
            />
          </label>
          <Button type="button" variant="primary" disabled={busy} onClick={register}>등록</Button>
        </div>
        <p style={{ margin: '0.7rem 0 0', color: '#6b7280', fontSize: '0.85rem' }}>
          {year}년 최저시급 {won(minimum)}이 기본값입니다. 알바마다 바꿀 수 있습니다.
          미신고는 주휴수당을 주지 않습니다.
        </p>
        {wageTouched && minimum > 0 && Number(wage || 0) < minimum && (
          <p style={{ margin: '0.35rem 0 0', color: '#92400e', fontSize: '0.85rem' }}>입력한 시급이 {year}년 최저시급보다 낮습니다.</p>
        )}
      </Card>

      <Card title="등록된 알바" style={{ marginBottom: '1rem' }}>
        {!calendar ? <Loading text="불러오는 중..." /> : calendar.workers.length === 0 ? (
          <p style={{ margin: 0, color: '#6b7280' }}>등록된 알바가 없습니다.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  {['이름', '주민번호', '구분', '시급', '주민번호 변경', ''].map((head) => <th key={head || 'actions'}>{head}</th>)}
                </tr>
              </thead>
              <tbody>
                {calendar.workers.map((worker) => {
                  const edit = edits[worker.id] || { name: worker.name, reported: worker.reported, hourly_wage: String(worker.hourly_wage), resident_id: '' };
                  return (
                    <tr key={worker.id} style={worker.active ? undefined : { opacity: 0.45 }}>
                      <td>
                        <input className="ui-control" value={edit.name} onChange={(event) => setEdits((current) => ({ ...current, [worker.id]: { ...edit, name: event.target.value } }))} />
                      </td>
                      <td>{worker.resident_id}</td>
                      <td>
                        <select
                          className="ui-control"
                          value={edit.reported ? 'reported' : 'unreported'}
                          onChange={(event) => setEdits((current) => ({ ...current, [worker.id]: { ...edit, reported: event.target.value === 'reported' } }))}
                        >
                          <option value="reported">신고</option>
                          <option value="unreported">미신고</option>
                        </select>
                      </td>
                      <td>
                        <input
                          className="ui-control"
                          type="number"
                          style={{ width: '7rem' }}
                          value={edit.hourly_wage}
                          onChange={(event) => setEdits((current) => ({ ...current, [worker.id]: { ...edit, hourly_wage: event.target.value } }))}
                        />
                      </td>
                      <td>
                        <input
                          className="ui-control"
                          style={{ width: '9rem' }}
                          placeholder="바꿀 때만"
                          value={edit.resident_id}
                          onChange={(event) => setEdits((current) => ({ ...current, [worker.id]: { ...edit, resident_id: event.target.value } }))}
                        />
                      </td>
                      <td style={{ whiteSpace: 'nowrap' }}>
                        <Button type="button" variant="secondary" disabled={busy} onClick={() => saveWorker(worker)}>저장</Button>
                        {worker.active ? (
                          <Button type="button" variant="ghost" disabled={busy} onClick={() => setActive(worker, false)}>그만둠</Button>
                        ) : (
                          <Button type="button" variant="ghost" disabled={busy} onClick={() => setActive(worker, true)}>다시 근무</Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="근무 달력" style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.75rem' }}>
          <Button type="button" variant="secondary" onClick={() => shiftMonth(-1)}>이전 달</Button>
          <strong>{year}년 {month}월</strong>
          <Button type="button" variant="secondary" onClick={() => shiftMonth(1)}>다음 달</Button>
        </div>
        <p style={{ margin: '0 0 0.75rem', color: '#6b7280', fontSize: '0.85rem' }}>
          날짜를 누르면 그 날의 알바별 근무시간을 적습니다. 한 주는 월요일부터 일요일입니다. 일요일에 나오는 주휴수당은 그 주 근무시간 합 ÷ 40 × 8 × 시급입니다.
        </p>
        {loading || !calendar ? <Loading text="불러오는 중..." /> : (
          <div style={{ border: '1px solid #dee2e6', borderRadius: 8, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', background: '#f8f9fa' }}>
              {WEEKDAYS.map((label, index) => (
                <div key={label} style={{
                  padding: '0.45rem', textAlign: 'center', fontWeight: 600, fontSize: '0.8rem',
                  color: index === 6 ? '#dc3545' : '#495057',
                  borderRight: index < 6 ? '1px solid #dee2e6' : 'none',
                }}>{label}</div>
              ))}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)' }}>
              {cells.map((day, index) => {
                const date = day ? `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}` : '';
                const entries = day ? calendar.days[date] || [] : [];
                const holidays = day ? holidayBySunday.get(date) || [] : [];
                const isToday = day === today.getDate() && month === today.getMonth() + 1 && year === today.getFullYear();
                const selectedDay = date && date === selected;
                return (
                  <button
                    key={index}
                    type="button"
                    disabled={!day}
                    onClick={() => day && chooseDay(date)}
                    style={{
                      minHeight: 108,
                      textAlign: 'left',
                      padding: '0.35rem',
                      border: 'none',
                      borderTop: '1px solid #dee2e6',
                      borderRight: index % 7 < 6 ? '1px solid #dee2e6' : 'none',
                      background: !day ? '#fafafa' : selectedDay ? '#e7f1ff' : index % 7 === 6 ? '#fff8f8' : 'white',
                      cursor: day ? 'pointer' : 'default',
                      font: 'inherit',
                    }}
                  >
                    {day && (
                      <>
                        <div style={{
                          fontSize: '0.8rem', fontWeight: isToday ? 700 : 500,
                          color: isToday ? 'white' : index % 7 === 6 ? '#dc3545' : '#212529',
                          background: isToday ? '#0d6efd' : 'transparent',
                          borderRadius: 11, width: 22, height: 22,
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                        }}>{day}</div>
                        {entries.map((entry) => (
                          <div key={entry.worker_id} style={{ fontSize: '0.72rem', marginTop: 2, color: entry.reported ? '#166534' : '#4b5563' }}>
                            {entry.name} {hoursText(entry.hours)}시간
                          </div>
                        ))}
                        {holidays.map((person) => (
                          <div key={`h-${person.worker_id}`} style={{ fontSize: '0.68rem', marginTop: 2, color: '#9a3412' }}>
                            {person.name} 주휴 {won(person.weekly_holiday_pay)}
                          </div>
                        ))}
                      </>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {selected && calendar && (
          <div style={{ marginTop: '1rem' }}>
            <strong>{selected} 근무시간</strong>
            <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginTop: '0.6rem', alignItems: 'end' }}>
              {calendar.workers.filter((worker) => worker.active || Object.prototype.hasOwnProperty.call(drafts, worker.id)).map((worker) => (
                <label key={worker.id} className="ops-label">
                  {worker.name} · {worker.reported ? '신고' : '미신고'}
                  <input
                    className="ui-control"
                    type="number"
                    min={0}
                    max={24}
                    step={0.5}
                    style={{ width: '6rem' }}
                    value={drafts[worker.id] ?? ''}
                    onChange={(event) => setDrafts((current) => ({ ...current, [worker.id]: event.target.value }))}
                  />
                </label>
              ))}
              <Button type="button" variant="primary" disabled={busy || calendar.workers.length === 0} onClick={saveDay}>이 날 기록</Button>
            </div>
            {calendar.workers.every((worker) => !worker.active) && (
              <p style={{ margin: '0.5rem 0 0', color: '#6b7280' }}>근무 중인 알바가 없습니다. 위에서 먼저 등록하세요.</p>
            )}
          </div>
        )}
      </Card>

      <Card title="이달 합계">
        {!calendar || calendar.totals.length === 0 ? (
          <p style={{ margin: 0, color: '#6b7280' }}>이 달에 기록된 근무가 없습니다.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  {['이름', '구분', '시급', '근무시간', '주휴시간', '주휴수당'].map((head) => <th key={head}>{head}</th>)}
                </tr>
              </thead>
              <tbody>
                {calendar.totals.map((row) => (
                  <tr key={row.worker_id}>
                    <td>{row.name}</td>
                    <td>{row.reported ? '신고' : '미신고'}</td>
                    <td>{won(row.hourly_wage)}</td>
                    <td>{hoursText(row.basic_hours)}</td>
                    <td>{hoursText(row.weekly_holiday_hours)}</td>
                    <td>{won(row.weekly_holiday_pay)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
