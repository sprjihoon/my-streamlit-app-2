'use client';

import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import PageHeader from '@/components/ui/page-header';
import { Select } from '@/components/ui/select';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface CalendarLeaver {
  request_id: number;
  nickname: string;
  department: string;
  position: string;
  leave_type: string;
  hours: number;
  status: 'approved' | 'pending' | 'cancel_requested';
}

interface CalendarData {
  year: number;
  month: number;
  is_admin?: boolean;
  days: Record<string, CalendarLeaver[]>;
  holidays: Record<string, string>;
}

const DEPT_COLORS: Record<string, string> = {
  '패션팀': '#0d6efd',
  '뷰티팀': '#9c27b0',
  '인사': '#198754',
};

function LeaveCalendar({
  year, month, calendarData, isAdmin, confirmingId, onConfirm,
}: {
  year: number;
  month: number;
  calendarData: CalendarData | null;
  isAdmin: boolean;
  confirmingId: number | null;
  onConfirm: (requestId: number) => void;
}) {

  if (!calendarData) return <div style={{ padding: '2rem', textAlign: 'center', color: '#6c757d' }}>달력 데이터를 불러오는 중...</div>;

  const firstDay = new Date(year, month - 1, 1).getDay();
  const daysInMonth = new Date(year, month, 0).getDate();
  const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

  const cells: (number | null)[] = [
    ...Array(firstDay).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  while (cells.length % 7 !== 0) cells.push(null);

  const today = new Date();
  const isCurrentMonth = today.getFullYear() === year && today.getMonth() + 1 === month;

  return (
    <div>
      {/* 범례 */}
      <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', marginBottom: '1rem', fontSize: '0.8rem', alignItems: 'center' }}>
        {Object.entries(DEPT_COLORS).map(([dept, color]) => (
          <div key={dept} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%', backgroundColor: color }} />
            <span>{dept}</span>
          </div>
        ))}
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <div style={{ width: 10, height: 10, borderRadius: '50%', backgroundColor: '#fd7e14' }} />
          <span>기타</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <div style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: '#fff3cd', border: '1px solid #ffc107' }} />
          <span>공휴일</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <div style={{ width: 26, height: 10, borderRadius: 2, border: '1.5px dashed #adb5bd', backgroundColor: '#f8f9fa' }} />
          <span style={{ color: '#6c757d' }}>결재중</span>
        </div>
      </div>

      {/* 달력 그리드 */}
      <div style={{ border: '1px solid #dee2e6', borderRadius: '8px', overflow: 'hidden' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', backgroundColor: '#f8f9fa' }}>
          {WEEKDAYS.map((w, i) => (
            <div key={w} style={{
              padding: '0.5rem', textAlign: 'center', fontWeight: 600, fontSize: '0.8rem',
              color: i === 0 ? '#dc3545' : i === 6 ? '#0d6efd' : '#495057',
              borderRight: i < 6 ? '1px solid #dee2e6' : 'none',
              borderBottom: '1px solid #dee2e6',
            }}>
              {w}
            </div>
          ))}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)' }}>
          {cells.map((day, idx) => {
            const col = idx % 7;
            const dateStr = day ? `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}` : '';
            const leavers = day && calendarData.days[dateStr] ? calendarData.days[dateStr] : [];
            const holidayName = day && calendarData.holidays[dateStr];
            const isToday = isCurrentMonth && day === today.getDate();
            const isWeekend = col === 0 || col === 6;

            const pendingLeavers = leavers.filter((leaver) => leaver.status === 'pending');
            const otherLeavers = leavers.filter((leaver) => leaver.status !== 'pending');
            const visibleOthers = otherLeavers.slice(0, 3);
            const hiddenCount = otherLeavers.length - visibleOthers.length;

            return (
              <div key={idx}
                style={{
                  minHeight: '90px',
                  padding: '0.4rem',
                  borderRight: col < 6 ? '1px solid #dee2e6' : 'none',
                  borderBottom: idx < cells.length - 7 ? '1px solid #dee2e6' : 'none',
                  backgroundColor: !day ? '#fafafa' : holidayName ? '#fff9e6' : isWeekend ? '#fafafa' : 'white',
                  position: 'relative',
                }}>
                {day && (
                  <>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.25rem' }}>
                      <span style={{
                        fontSize: '0.8rem', fontWeight: isToday ? 700 : 400,
                        color: isToday ? 'white' : col === 0 ? '#dc3545' : col === 6 ? '#0d6efd' : '#212529',
                        backgroundColor: isToday ? '#0d6efd' : 'transparent',
                        borderRadius: isToday ? '50%' : 0,
                        width: isToday ? '22px' : 'auto',
                        height: isToday ? '22px' : 'auto',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        lineHeight: 1,
                      } as React.CSSProperties}>
                        {day}
                      </span>
                      {leavers.length > 0 && (
                        <span style={{
                          fontSize: '0.7rem', fontWeight: 700,
                          backgroundColor: '#dc3545', color: 'white',
                          borderRadius: '10px', padding: '1px 5px', minWidth: '18px', textAlign: 'center',
                        }}>
                          {leavers.length}
                        </span>
                      )}
                    </div>

                    {holidayName && (
                      <div style={{ fontSize: '0.65rem', color: '#856404', marginBottom: '0.2rem', fontWeight: 500 }}>
                        {holidayName}
                      </div>
                    )}

                    {pendingLeavers.map((leaver) => {
                      const isHalf = leaver.leave_type.includes('반차');
                      const label = `${leaver.nickname}${isHalf ? '(반)' : ''}`;
                      if (!isAdmin) {
                        return (
                          <div key={leaver.request_id} style={{
                            fontSize: '0.68rem',
                            padding: '1px 5px',
                            marginBottom: '2px',
                            borderRadius: '3px',
                            backgroundColor: '#f8f9fa',
                            color: '#6c757d',
                            borderLeft: '3px dashed #adb5bd',
                            fontWeight: 500,
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                          }}>
                            {label}?
                          </div>
                        );
                      }
                      return (
                        <button
                          key={leaver.request_id}
                          type="button"
                          disabled={confirmingId === leaver.request_id}
                          onClick={() => onConfirm(leaver.request_id)}
                          style={{
                            display: 'block',
                            width: '100%',
                            textAlign: 'left',
                            fontSize: '0.68rem',
                            padding: '2px 5px',
                            marginBottom: '2px',
                            borderRadius: '3px',
                            backgroundColor: '#fff3e0',
                            color: '#9a3412',
                            border: '1px solid #fd7e14',
                            fontWeight: 600,
                            cursor: confirmingId === leaver.request_id ? 'wait' : 'pointer',
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                          }}
                        >
                          {confirmingId === leaver.request_id ? '확정 중' : `${label} 확정`}
                        </button>
                      );
                    })}
                    {visibleOthers.map((leaver, i) => {
                      const color = DEPT_COLORS[leaver.department] || '#fd7e14';
                      const isHalf = leaver.leave_type.includes('반차');
                      return (
                        <div key={`${leaver.request_id}-${i}`} style={{
                          fontSize: '0.68rem',
                          padding: '1px 5px',
                          marginBottom: '2px',
                          borderRadius: '3px',
                          backgroundColor: color + '20',
                          color,
                          borderLeft: `3px solid ${color}`,
                          fontWeight: 500,
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          opacity: isHalf ? 0.7 : 1,
                        }}>
                          {leaver.nickname}{isHalf ? '(반)' : ''}
                        </div>
                      );
                    })}
                    {hiddenCount > 0 && (
                      <div style={{ fontSize: '0.65rem', color: '#6c757d' }}>+{hiddenCount}명 더</div>
                    )}
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>

    </div>
  );
}

export default function LeaveCalendarPage() {
  const [year, setYear] = useState(new Date().getFullYear());
  const [month, setMonth] = useState(new Date().getMonth() + 1);
  const [calendarData, setCalendarData] = useState<CalendarData | null>(null);
  const [token, setToken] = useState('');
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [notice, setNotice] = useState('');
  const [noticeError, setNoticeError] = useState(false);

  useEffect(() => {
    const t = localStorage.getItem('token') || '';
    setToken(t);
  }, []);

  const fetchCalendarData = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_URL}/leave/calendar?token=${token}&year=${year}&month=${month}`);
      if (res.ok) setCalendarData(await res.json());
    } catch {}
  }, [token, year, month]);

  useEffect(() => {
    if (token) fetchCalendarData();
  }, [token, fetchCalendarData]);

  async function confirmRequest(requestId: number) {
    setNotice('');
    setNoticeError(false);
    setConfirmingId(requestId);
    try {
      const res = await fetch(`${API_URL}/leave/calendar/${requestId}/confirm?token=${token}`, { method: 'POST' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || '확정 실패');
      setNotice(data.message || '연차 신청을 확정했습니다.');
      await fetchCalendarData();
    } catch (err) {
      setNoticeError(true);
      setNotice(err instanceof Error ? err.message : '확정 실패');
    } finally {
      setConfirmingId(null);
    }
  }

  const card: React.CSSProperties = {
    backgroundColor: 'white', borderRadius: '8px', padding: '1.5rem',
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
  };

  return (
    <div>
      <PageHeader title="연차 달력" subtitle="결재중 이름은 달력 칸에서 바로 확정할 수 있습니다." />
      {notice && <div style={{ marginBottom: '0.75rem', color: noticeError ? '#dc3545' : '#198754' }}>{notice}</div>}

      <div style={card}>
        {/* 헤더: 월 이동 */}
        <div className="tw-mb-5 tw-flex tw-flex-wrap tw-items-end tw-justify-between tw-gap-3">
          <h4 className="tw-m-0">{year}년 {month}월</h4>
          <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-2">
            <Select value={year} onChange={e => setYear(Number(e.target.value))} className="tw-max-w-[110px]">
              {[2024, 2025, 2026, 2027].map(y => <option key={y} value={y}>{y}년</option>)}
            </Select>
            <Select value={month} onChange={e => setMonth(Number(e.target.value))} className="tw-max-w-[90px]">
              {Array.from({ length: 12 }, (_, i) => i + 1).map(m => (
                <option key={m} value={m}>{m}월</option>
              ))}
            </Select>
            <Button type="button" variant="secondary" onClick={() => { const d = new Date(year, month - 2); setYear(d.getFullYear()); setMonth(d.getMonth() + 1); }}>이전</Button>
            <Button type="button" variant="secondary" onClick={() => { setYear(new Date().getFullYear()); setMonth(new Date().getMonth() + 1); }}>오늘</Button>
            <Button type="button" variant="secondary" onClick={() => { const d = new Date(year, month); setYear(d.getFullYear()); setMonth(d.getMonth() + 1); }}>다음</Button>
          </div>
        </div>

        <LeaveCalendar
          year={year}
          month={month}
          calendarData={calendarData}
          isAdmin={!!calendarData?.is_admin}
          confirmingId={confirmingId}
          onConfirm={confirmRequest}
        />

        {/* 이번달 휴가자 요약 */}
        {calendarData && Object.keys(calendarData.days).length > 0 && (
          <div style={{ marginTop: '1.5rem', paddingTop: '1rem', borderTop: '1px solid #dee2e6' }}>
            <h5 style={{ margin: '0 0 0.75rem 0', color: '#495057' }}>{month}월 연차 신청자</h5>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
              {(() => {
                const personMap: Record<number, { name: string; days: string[]; dept: string; status: string }> = {};
                Object.entries(calendarData.days).forEach(([date, leavers]) => {
                  leavers.forEach(l => {
                    if (!personMap[l.request_id]) personMap[l.request_id] = { name: l.nickname, days: [], dept: l.department, status: l.status };
                    if (!personMap[l.request_id].days.includes(date)) personMap[l.request_id].days.push(date);
                  });
                });
                return Object.entries(personMap).map(([requestId, info]) => {
                  const color = DEPT_COLORS[info.dept] || '#fd7e14';
                  const isPending = info.status === 'pending';
                  return (
                    <div key={requestId} style={{
                      padding: '0.4rem 0.75rem', borderRadius: '6px',
                      backgroundColor: color + '15', border: `1px solid ${isPending ? '#adb5bd' : color}40`,
                      fontSize: '0.8rem',
                      opacity: isPending ? 0.8 : 1,
                      display: 'flex', alignItems: 'center', gap: '0.35rem',
                    }}>
                      <span style={{ fontWeight: 600, color }}>{info.name}</span>
                      <span style={{ color: '#6c757d' }}>{info.dept}</span>
                      <span style={{ color: '#495057' }}>{info.days.length}일</span>
                      {isPending && <span style={{ fontSize: '0.7rem', color: '#fd7e14' }}>결재중</span>}
                      {calendarData.is_admin && isPending && (
                        <Button type="button" variant="primary" disabled={confirmingId === Number(requestId)} onClick={() => confirmRequest(Number(requestId))}>
                          {confirmingId === Number(requestId) ? '확정 중' : '확정'}
                        </Button>
                      )}
                    </div>
                  );
                });
              })()}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
