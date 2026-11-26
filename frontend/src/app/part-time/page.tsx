'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert } from '@/components/Alert';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import PageHeader from '@/components/ui/page-header';
import { Button } from '@/components/ui/button';
import { API, CalendarData, DayEntry, Worker, apiError, downloadPartTimeExcel, hoursText, readAdmin, won } from './model';

const WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일'];

interface WorkerDraft {
  id: number | null;
  name: string;
  residentId: string;
  reported: boolean;
  wage: string;
  leaving: boolean;
}

interface HourDraft {
  date: string;
  workerId: number;
  name: string;
  hours: string;
  existing: boolean;
}

export default function PartTimePage() {
  const now = new Date();
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [calendar, setCalendar] = useState<CalendarData | null>(null);
  const [workerDraft, setWorkerDraft] = useState<WorkerDraft | null>(null);
  const [recallOpen, setRecallOpen] = useState(false);
  const [hourDraft, setHourDraft] = useState<HourDraft | null>(null);
  const draggingId = useRef<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const load = useCallback(async (nextYear: number, nextMonth: number) => {
    const token = localStorage.getItem('token') || '';
    setLoading(true);
    setError(null);
    const res = await fetch(`${API}/part-time/calendar?token=${encodeURIComponent(token)}&year=${nextYear}&month=${nextMonth}`);
    setLoading(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    setCalendar(await res.json());
  }, []);

  useEffect(() => {
    const admin = readAdmin();
    setIsAdmin(admin);
    if (admin) load(year, month);
    else setLoading(false);
  }, [load, year, month]);

  function shiftMonth(delta: number) {
    const next = new Date(year, month - 1 + delta, 1);
    setYear(next.getFullYear());
    setMonth(next.getMonth() + 1);
  }

  function openRegister() {
    setWorkerDraft({
      id: null,
      name: '',
      residentId: '',
      reported: true,
      wage: String(calendar?.minimum_wage || ''),
      leaving: false,
    });
  }

  function openEdit(worker: Worker) {
    setWorkerDraft({
      id: worker.id,
      name: worker.name,
      residentId: '',
      reported: worker.reported,
      wage: String(worker.hourly_wage),
      leaving: false,
    });
  }

  async function saveWorker() {
    if (!workerDraft) return;
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    setSuccess(null);
    const creating = workerDraft.id === null;
    const body: Record<string, string | number | boolean> = {
      name: workerDraft.name,
      reported: workerDraft.reported,
      hourly_wage: Number(workerDraft.wage || 0),
    };
    if (creating || workerDraft.residentId.trim()) body.resident_id = workerDraft.residentId.trim();
    const res = await fetch(
      `${API}/part-time/workers${creating ? '' : `/${workerDraft.id}`}?token=${encodeURIComponent(token)}`,
      { method: creating ? 'POST' : 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
    );
    setBusy(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    setWorkerDraft(null);
    setSuccess(creating ? '알바를 등록했습니다.' : '알바 정보를 저장했습니다.');
    await load(year, month);
  }

  async function setActive(workerId: number, active: boolean, name: string) {
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    setSuccess(null);
    const res = await fetch(`${API}/part-time/workers/${workerId}?token=${encodeURIComponent(token)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    setWorkerDraft(null);
    setSuccess(active ? `${name} 님을 다시 불러왔습니다.` : `${name} 님을 그만둔 알바로 옮겼습니다. 다시 불러오기에서 되돌릴 수 있습니다.`);
    await load(year, month);
  }

  function dropWorker(date: string, workerId: number) {
    if (!calendar) return;
    const worker = calendar.workers.find((item) => item.id === workerId);
    if (!worker || !worker.active) return;
    const exists = (calendar.days[date] || []).some((item) => item.worker_id === workerId);
    if (exists) {
      setSuccess(null);
      setError(`${worker.name} 님은 이 날짜에 이미 들어가 있습니다.`);
      return;
    }
    setError(null);
    setHourDraft({ date, workerId, name: worker.name, hours: '', existing: false });
  }

  function editHours(date: string, entry: DayEntry) {
    setHourDraft({ date, workerId: entry.worker_id, name: entry.name, hours: hoursText(entry.hours), existing: true });
  }

  async function saveHours(remove: boolean) {
    if (!hourDraft) return;
    const hours = remove ? 0 : Number(hourDraft.hours || 0);
    if (!remove && hours <= 0) {
      setError('근무시간을 입력하세요.');
      return;
    }
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    setSuccess(null);
    const res = await fetch(`${API}/part-time/days?token=${encodeURIComponent(token)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ work_date: hourDraft.date, entries: [{ worker_id: hourDraft.workerId, hours }] }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    setCalendar(await res.json());
    setHourDraft(null);
    setSuccess(remove ? `${hourDraft.date}에서 ${hourDraft.name}을 뺐습니다.` : `${hourDraft.date} ${hourDraft.name} ${hoursText(hours)}시간을 기록했습니다.`);
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
  const activeWorkers = (calendar?.workers || []).filter((worker) => worker.active);
  const inactiveWorkers = (calendar?.workers || []).filter((worker) => !worker.active);

  return (
    <div>
      <PageHeader
        title="관리대장"
        subtitle="알바를 달력으로 끌어다 놓으면 그 날 근무시간을 적습니다. 같은 알바는 같은 날에 한 번만 들어갑니다."
        actions={(
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <Button type="button" variant="secondary" onClick={() => setRecallOpen(true)}>
              그만둔 알바 다시 불러오기{inactiveWorkers.length > 0 ? ` (${inactiveWorkers.length})` : ''}
            </Button>
            <Button type="button" variant="primary" onClick={openRegister}>알바 등록</Button>
          </div>
        )}
      />
      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}
      {success && <Alert type="success" message={success} onClose={() => setSuccess(null)} />}

      <Card title="등록된 알바" style={{ marginBottom: '1rem' }}>
        {loading && !calendar ? <Loading text="불러오는 중..." /> : activeWorkers.length === 0 ? (
          <p style={{ margin: 0, color: '#6b7280' }}>근무 중인 알바가 없습니다. 알바 등록으로 추가하세요.</p>
        ) : (
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            {activeWorkers.map((worker) => (
              <div key={worker.id} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', border: '1px solid #d1d5db', borderRadius: 8, padding: '0.35rem 0.45rem', background: 'white' }}>
                <div
                  draggable
                  onDragStart={(event) => {
                    draggingId.current = worker.id;
                    event.dataTransfer.setData('text/plain', String(worker.id));
                    event.dataTransfer.effectAllowed = 'copy';
                  }}
                  onDragEnd={() => { draggingId.current = null; }}
                  style={{ cursor: 'grab', fontSize: '0.9rem' }}
                  title="달력 날짜로 끌어다 놓으세요"
                >
                  <strong>{worker.name}</strong>
                  <span style={{ marginLeft: 6, color: worker.reported ? '#166534' : '#6b7280', fontSize: '0.75rem' }}>
                    {worker.reported ? '신고' : '미신고'}
                  </span>
                  <span style={{ marginLeft: 6, color: '#374151', fontSize: '0.75rem' }}>{won(worker.hourly_wage)}</span>
                </div>
                <Button type="button" variant="ghost" onClick={() => openEdit(worker)}>수정</Button>
              </div>
            ))}
          </div>
        )}
        {inactiveWorkers.length > 0 && (
          <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <span style={{ color: '#6b7280', fontSize: '0.85rem' }}>그만둔 알바</span>
            {inactiveWorkers.map((worker) => (
              <Button key={worker.id} type="button" variant="ghost" disabled={busy} onClick={() => setActive(worker.id, true, worker.name)}>
                {worker.name} 다시 불러오기
              </Button>
            ))}
          </div>
        )}
      </Card>

      <Card title="근무 달력">
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.75rem' }}>
          <Button type="button" variant="secondary" onClick={() => shiftMonth(-1)}>이전 달</Button>
          <strong>{year}년 {month}월</strong>
          <Button type="button" variant="secondary" onClick={() => shiftMonth(1)}>다음 달</Button>
          <Button type="button" variant="secondary" disabled={busy} onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              await downloadPartTimeExcel(year, month);
            } catch (caught) {
              setError(caught instanceof Error ? caught.message : '엑셀을 받지 못했습니다.');
            }
            setBusy(false);
          }}>노무사 전달용 엑셀</Button>
        </div>
        <p style={{ margin: '0 0 0.75rem', color: '#6b7280', fontSize: '0.85rem' }}>
          초록은 신고, 회색은 미신고입니다. 금액은 그날 시급에 근무시간을 곱한 값이고, 일요일의 주휴는 신고 알바만 표시됩니다. 이름을 누르면 시간을 고치거나 뺄 수 있습니다.
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
                const entries = day && calendar.days[date] ? calendar.days[date] : [];
                const holidays = day ? holidayBySunday.get(date) || [] : [];
                const dayPay = entries.reduce((sum, entry) => sum + entry.pay, 0) + holidays.reduce((sum, person) => sum + person.weekly_holiday_pay, 0);
                const isToday = day === today.getDate() && month === today.getMonth() + 1 && year === today.getFullYear();
                return (
                  <div
                    key={index}
                    onDragOver={(event) => {
                      if (!day || draggingId.current === null) return;
                      event.preventDefault();
                      event.dataTransfer.dropEffect = 'copy';
                      event.currentTarget.style.outline = '2px solid #0d6efd';
                    }}
                    onDragLeave={(event) => { event.currentTarget.style.outline = ''; }}
                    onDrop={(event) => {
                      if (!day) return;
                      event.preventDefault();
                      event.currentTarget.style.outline = '';
                      const workerId = draggingId.current || Number(event.dataTransfer.getData('text/plain'));
                      draggingId.current = null;
                      if (workerId) dropWorker(date, workerId);
                    }}
                    style={{
                      minHeight: 124,
                      padding: '0.35rem',
                      borderTop: '1px solid #dee2e6',
                      borderRight: index % 7 < 6 ? '1px solid #dee2e6' : 'none',
                      background: !day ? '#fafafa' : index % 7 === 6 ? '#fff8f8' : 'white',
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
                          <button
                            key={entry.worker_id}
                            type="button"
                            onDragOver={(event) => event.preventDefault()}
                            onClick={() => editHours(date, entry)}
                            style={{
                              display: 'block', width: '100%', textAlign: 'left', marginTop: 3,
                              border: 0, background: entry.reported ? '#dcfce7' : '#f3f4f6',
                              color: entry.reported ? '#166534' : '#374151',
                              borderRadius: 4, padding: '2px 4px', font: 'inherit', fontSize: '0.72rem', cursor: 'pointer',
                            }}
                          >
                            {entry.name} {hoursText(entry.hours)}시간
                            <div>{won(entry.pay)}</div>
                          </button>
                        ))}
                        {holidays.map((person) => (
                          <div key={`h-${person.worker_id}`} style={{ fontSize: '0.68rem', marginTop: 3, color: '#9a3412' }}>
                            {person.name} 주휴 {won(person.weekly_holiday_pay)}
                          </div>
                        ))}
                        {dayPay > 0 && <div style={{ marginTop: 4, fontSize: '0.72rem', fontWeight: 700 }}>일계 {won(dayPay)}</div>}
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </Card>

      {workerDraft && (
        <div className="data-modal-backdrop" onClick={() => setWorkerDraft(null)}>
          <div className="data-modal" style={{ maxWidth: 480 }} role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <div className="data-modal-head">
              <h2>{workerDraft.id === null ? '알바 등록' : '알바 수정'}</h2>
              <Button type="button" variant="ghost" onClick={() => setWorkerDraft(null)}>닫기</Button>
            </div>
            <div className="data-modal-body">
              <div className="data-form-grid">
                <label className="ops-label">
                  이름
                  <input className="ui-control" value={workerDraft.name} onChange={(event) => setWorkerDraft({ ...workerDraft, name: event.target.value })} />
                </label>
                <label className="ops-label">
                  주민번호
                  <input
                    className="ui-control"
                    placeholder={workerDraft.id === null ? '900101-1234567' : '바꿀 때만 입력'}
                    value={workerDraft.residentId}
                    onChange={(event) => setWorkerDraft({ ...workerDraft, residentId: event.target.value })}
                  />
                </label>
                <label className="ops-label">
                  구분
                  <select className="ui-control" value={workerDraft.reported ? 'reported' : 'unreported'} onChange={(event) => setWorkerDraft({ ...workerDraft, reported: event.target.value === 'reported' })}>
                    <option value="reported">신고</option>
                    <option value="unreported">미신고</option>
                  </select>
                </label>
                <label className="ops-label">
                  시급
                  <input className="ui-control" type="number" min={1} value={workerDraft.wage} onChange={(event) => setWorkerDraft({ ...workerDraft, wage: event.target.value })} />
                </label>
              </div>
              <p style={{ margin: '0.75rem 0 0', color: '#6b7280', fontSize: '0.85rem' }}>
                {year}년 최저시급은 {won(minimum)}입니다. 미신고는 주휴수당이 없습니다.
              </p>
              {Number(workerDraft.wage || 0) > 0 && Number(workerDraft.wage) < minimum && (
                <p style={{ margin: '0.35rem 0 0', color: '#92400e', fontSize: '0.85rem' }}>입력한 시급이 {year}년 최저시급보다 낮습니다.</p>
              )}
              {workerDraft.leaving && (
                <p style={{ margin: '0.75rem 0 0', color: '#92400e' }}>그만둔 알바는 달력에 새로 올릴 수 없습니다. 지난 근무 기록은 남고, 다시 불러오기에서 되돌릴 수 있습니다.</p>
              )}
            </div>
            <div className="data-modal-foot">
              {workerDraft.id !== null && !workerDraft.leaving && (
                <Button type="button" variant="ghost" disabled={busy} onClick={() => setWorkerDraft({ ...workerDraft, leaving: true })}>그만둠</Button>
              )}
              {workerDraft.leaving && (
                <Button type="button" variant="danger" disabled={busy} onClick={() => workerDraft.id !== null && setActive(workerDraft.id, false, workerDraft.name)}>그만둠 확인</Button>
              )}
              <Button type="button" variant="primary" disabled={busy} onClick={saveWorker}>저장</Button>
            </div>
          </div>
        </div>
      )}

      {recallOpen && (
        <div className="data-modal-backdrop" onClick={() => setRecallOpen(false)}>
          <div className="data-modal" style={{ maxWidth: 520 }} role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <div className="data-modal-head">
              <h2>그만둔 알바 다시 불러오기</h2>
              <Button type="button" variant="ghost" onClick={() => setRecallOpen(false)}>닫기</Button>
            </div>
            <div className="data-modal-body">
              {inactiveWorkers.length === 0 ? (
                <p style={{ margin: 0, color: '#6b7280' }}>그만둔 알바가 없습니다.</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {inactiveWorkers.map((worker) => (
                    <div key={worker.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.75rem', border: '1px solid #e5e7eb', borderRadius: 8, padding: '0.6rem 0.75rem' }}>
                      <div>
                        <strong>{worker.name}</strong>
                        <span style={{ marginLeft: 8, color: worker.reported ? '#166534' : '#6b7280', fontSize: '0.8rem' }}>
                          {worker.reported ? '신고' : '미신고'}
                        </span>
                        <div style={{ color: '#6b7280', fontSize: '0.8rem' }}>시급 {won(worker.hourly_wage)} · {worker.resident_id}</div>
                      </div>
                      <Button type="button" variant="primary" disabled={busy} onClick={() => setActive(worker.id, true, worker.name)}>다시 불러오기</Button>
                    </div>
                  ))}
                </div>
              )}
              <p style={{ margin: '0.75rem 0 0', color: '#6b7280', fontSize: '0.85rem' }}>다시 불러오면 달력에 근무를 올릴 수 있습니다. 지난 근무 기록은 그대로입니다.</p>
            </div>
          </div>
        </div>
      )}

      {hourDraft && (
        <div className="data-modal-backdrop" onClick={() => setHourDraft(null)}>
          <div className="data-modal" style={{ maxWidth: 420 }} role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <div className="data-modal-head">
              <h2>{hourDraft.date} {hourDraft.name}</h2>
              <Button type="button" variant="ghost" onClick={() => setHourDraft(null)}>닫기</Button>
            </div>
            <div className="data-modal-body">
              <label className="ops-label">
                근무시간
                <input
                  className="ui-control"
                  type="number"
                  min={0.5}
                  max={24}
                  step={0.5}
                  autoFocus
                  value={hourDraft.hours}
                  onChange={(event) => setHourDraft({ ...hourDraft, hours: event.target.value })}
                />
              </label>
              <p style={{ margin: '0.7rem 0 0', color: '#6b7280', fontSize: '0.85rem' }}>실제 근무한 시간을 적습니다. 같은 알바를 같은 날에 다시 올리면 추가되지 않습니다.</p>
            </div>
            <div className="data-modal-foot">
              {hourDraft.existing && (
                <Button type="button" variant="danger" disabled={busy} onClick={() => saveHours(true)}>이 날에서 빼기</Button>
              )}
              <Button type="button" variant="primary" disabled={busy} onClick={() => saveHours(false)}>기록</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
