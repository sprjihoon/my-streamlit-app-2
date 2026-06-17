'use client';

import { useState, useEffect, useCallback } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface CalendarLeaver {
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
  days: Record<string, CalendarLeaver[]>;
  holidays: Record<string, string>;
}

const DEPT_COLORS: Record<string, string> = {
  '패션팀': '#0d6efd',
  '뷰티팀': '#9c27b0',
  '인사': '#198754',
};

function LeaveCalendar({ year, month, calendarData }: { year: number; month: number; calendarData: CalendarData | null }) {
  const [tooltip, setTooltip] = useState<{ date: string; x: number; y: number } | null>(null);

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

            return (
              <div key={idx}
                onMouseEnter={leavers.length > 0 ? (e) => setTooltip({ date: dateStr, x: e.clientX, y: e.clientY }) : undefined}
                onMouseLeave={() => setTooltip(null)}
                style={{
                  minHeight: '90px',
                  padding: '0.4rem',
                  borderRight: col < 6 ? '1px solid #dee2e6' : 'none',
                  borderBottom: idx < cells.length - 7 ? '1px solid #dee2e6' : 'none',
                  backgroundColor: !day ? '#fafafa' : holidayName ? '#fff9e6' : isWeekend ? '#fafafa' : 'white',
                  position: 'relative',
                  cursor: leavers.length > 0 ? 'pointer' : 'default',
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

                    {leavers.slice(0, 3).map((leaver, i) => {
                      const color = DEPT_COLORS[leaver.department] || '#fd7e14';
                      const isHalf = leaver.leave_type.includes('반차');
                      const isPending = leaver.status === 'pending';
                      return (
                        <div key={i} style={{
                          fontSize: '0.68rem',
                          padding: '1px 5px',
                          marginBottom: '2px',
                          borderRadius: '3px',
                          backgroundColor: isPending ? '#f8f9fa' : color + '20',
                          color: isPending ? '#6c757d' : color,
                          borderLeft: isPending ? '3px dashed #adb5bd' : `3px solid ${color}`,
                          fontWeight: 500,
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          opacity: isHalf ? 0.7 : 1,
                        }}>
                          {leaver.nickname}{isHalf ? '(반)' : ''}{isPending ? '?' : ''}
                        </div>
                      );
                    })}
                    {leavers.length > 3 && (
                      <div style={{ fontSize: '0.65rem', color: '#6c757d' }}>+{leavers.length - 3}명 더</div>
                    )}
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* 툴팁 */}
      {tooltip && calendarData.days[tooltip.date] && (
        <div style={{
          position: 'fixed', top: tooltip.y + 12, left: Math.min(tooltip.x, window.innerWidth - 220),
          backgroundColor: 'white', border: '1px solid #dee2e6', borderRadius: '8px',
          padding: '0.75rem', boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
          zIndex: 1000, minWidth: '200px', maxWidth: '280px',
          pointerEvents: 'none',
        }}>
          <div style={{ fontWeight: 600, marginBottom: '0.5rem', fontSize: '0.875rem' }}>
            {tooltip.date} 휴가자 {calendarData.days[tooltip.date].length}명
          </div>
          {calendarData.days[tooltip.date].map((l, i) => (
            <div key={i} style={{ fontSize: '0.8rem', padding: '3px 0', borderBottom: i < calendarData.days[tooltip.date].length - 1 ? '1px solid #f0f0f0' : 'none' }}>
              <span style={{ fontWeight: 500 }}>{l.nickname}</span>
              <span style={{ color: '#6c757d', marginLeft: '0.5rem' }}>{l.department}</span>
              <span style={{
                marginLeft: '0.5rem', fontSize: '0.7rem', padding: '1px 5px',
                backgroundColor: (DEPT_COLORS[l.department] || '#fd7e14') + '20',
                color: DEPT_COLORS[l.department] || '#fd7e14',
                borderRadius: '3px',
              }}>
                {l.leave_type}
              </span>
              {l.status === 'pending' && (
                <span style={{ marginLeft: '0.4rem', fontSize: '0.65rem', color: '#fd7e14', backgroundColor: '#fff3e0', padding: '1px 4px', borderRadius: '3px' }}>결재중</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function LeaveCalendarPage() {
  const [year, setYear] = useState(new Date().getFullYear());
  const [month, setMonth] = useState(new Date().getMonth() + 1);
  const [calendarData, setCalendarData] = useState<CalendarData | null>(null);
  const [token, setToken] = useState('');

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

  const card: React.CSSProperties = {
    backgroundColor: 'white', borderRadius: '8px', padding: '1.5rem',
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
  };

  return (
    <div style={{ padding: '1.5rem', maxWidth: '1100px' }}>
      <h2 style={{ marginBottom: '0.5rem', fontSize: '1.375rem', fontWeight: 700, color: 'var(--text-primary)' }}>연차 달력</h2>
      <p style={{ color: '#6c757d', marginBottom: '1.5rem', fontSize: '0.875rem' }}>
        승인된 연차를 달력으로 확인합니다.
      </p>

      <div style={card}>
        {/* 헤더: 월 이동 */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem', flexWrap: 'wrap', gap: '0.75rem' }}>
          <h4 style={{ margin: 0 }}>{year}년 {month}월</h4>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <select value={year} onChange={e => setYear(Number(e.target.value))}
              style={{ padding: '0.4rem 0.75rem', border: '1px solid #dee2e6', borderRadius: '4px', fontSize: '0.875rem' }}>
              {[2024, 2025, 2026, 2027].map(y => <option key={y} value={y}>{y}년</option>)}
            </select>
            <select value={month} onChange={e => setMonth(Number(e.target.value))}
              style={{ padding: '0.4rem 0.75rem', border: '1px solid #dee2e6', borderRadius: '4px', fontSize: '0.875rem' }}>
              {Array.from({ length: 12 }, (_, i) => i + 1).map(m => (
                <option key={m} value={m}>{m}월</option>
              ))}
            </select>
            <button
              onClick={() => { const d = new Date(year, month - 2); setYear(d.getFullYear()); setMonth(d.getMonth() + 1); }}
              style={{ padding: '0.4rem 0.9rem', border: '1px solid #dee2e6', borderRadius: '4px', backgroundColor: 'white', cursor: 'pointer' }}>
              ◀
            </button>
            <button
              onClick={() => { setYear(new Date().getFullYear()); setMonth(new Date().getMonth() + 1); }}
              style={{ padding: '0.4rem 0.75rem', border: '1px solid #dee2e6', borderRadius: '4px', backgroundColor: 'white', cursor: 'pointer', fontSize: '0.875rem' }}>
              오늘
            </button>
            <button
              onClick={() => { const d = new Date(year, month); setYear(d.getFullYear()); setMonth(d.getMonth() + 1); }}
              style={{ padding: '0.4rem 0.9rem', border: '1px solid #dee2e6', borderRadius: '4px', backgroundColor: 'white', cursor: 'pointer' }}>
              ▶
            </button>
          </div>
        </div>

        <LeaveCalendar year={year} month={month} calendarData={calendarData} />

        {/* 이번달 휴가자 요약 */}
        {calendarData && Object.keys(calendarData.days).length > 0 && (
          <div style={{ marginTop: '1.5rem', paddingTop: '1rem', borderTop: '1px solid #dee2e6' }}>
            <h5 style={{ margin: '0 0 0.75rem 0', color: '#495057' }}>{month}월 연차 신청자</h5>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
              {(() => {
                const personMap: Record<string, { days: string[]; dept: string; type: string; status: string }> = {};
                Object.entries(calendarData.days).forEach(([date, leavers]) => {
                  leavers.forEach(l => {
                    if (!personMap[l.nickname]) personMap[l.nickname] = { days: [], dept: l.department, type: l.leave_type, status: l.status };
                    if (!personMap[l.nickname].days.includes(date)) personMap[l.nickname].days.push(date);
                    // approved가 하나라도 있으면 approved로
                    if (l.status === 'approved') personMap[l.nickname].status = 'approved';
                  });
                });
                return Object.entries(personMap).map(([name, info]) => {
                  const color = DEPT_COLORS[info.dept] || '#fd7e14';
                  const isPending = info.status === 'pending';
                  return (
                    <div key={name} style={{
                      padding: '0.4rem 0.75rem', borderRadius: '6px',
                      backgroundColor: color + '15', border: `1px solid ${isPending ? '#adb5bd' : color}40`,
                      fontSize: '0.8rem',
                      opacity: isPending ? 0.8 : 1,
                    }}>
                      <span style={{ fontWeight: 600, color }}>{name}</span>
                      <span style={{ color: '#6c757d', marginLeft: '0.4rem' }}>{info.dept}</span>
                      <span style={{ color: '#495057', marginLeft: '0.4rem' }}>{info.days.length}일</span>
                      {isPending && <span style={{ marginLeft: '0.3rem', fontSize: '0.7rem', color: '#fd7e14' }}>결재중</span>}
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
