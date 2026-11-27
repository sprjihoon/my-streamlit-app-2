'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert } from '@/components/Alert';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import PageHeader from '@/components/ui/page-header';
import { Button } from '@/components/ui/button';
import { API, CalendarData, apiError, canManagePartTime, hoursText, won } from '../model';

const WEEK = ['일', '월', '화', '수', '목', '금', '토'];

export default function PartTimeStatsPage() {
  const now = new Date();
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [workerId, setWorkerId] = useState(0);
  const [calendar, setCalendar] = useState<CalendarData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
    const allowedNow = canManagePartTime();
    setAllowed(allowedNow);
    if (allowedNow) load(year, month);
    else setLoading(false);
  }, [load, year, month]);

  function shiftMonth(delta: number) {
    const next = new Date(year, month - 1 + delta, 1);
    setYear(next.getFullYear());
    setMonth(next.getMonth() + 1);
  }

  const people = useMemo(() => {
    if (!calendar) return [];
    return calendar.totals.filter((row) => !workerId || row.worker_id === workerId);
  }, [calendar, workerId]);

  const days = useMemo(() => {
    if (!calendar) return [];
    const holidayBySunday = new Map(calendar.weeks.map((week) => [week.sunday, week.workers]));
    const dates = new Set<string>([...Object.keys(calendar.days), ...calendar.weeks.map((week) => week.sunday)]);
    return [...dates].sort().map((date) => {
      const entries = (calendar.days[date] || []).filter((entry) => !workerId || entry.worker_id === workerId);
      const holidayPay = (holidayBySunday.get(date) || [])
        .filter((person) => (!workerId || person.worker_id === workerId) && person.weekly_holiday_pay > 0)
        .reduce((sum, person) => sum + person.weekly_holiday_pay, 0);
      const hours = entries.reduce((sum, entry) => sum + entry.hours, 0);
      const workPay = entries.reduce((sum, entry) => sum + entry.pay, 0);
      if (entries.length === 0 && holidayPay === 0) return null;
      const parsed = new Date(`${date}T00:00:00`);
      return {
        date,
        label: `${parsed.getMonth() + 1}월 ${parsed.getDate()}일 (${WEEK[parsed.getDay()]})`,
        names: entries.map((entry) => entry.name),
        headcount: entries.length,
        hours,
        workPay,
        holidayPay,
        total: workPay + holidayPay,
      };
    }).filter((row): row is NonNullable<typeof row> => row !== null);
  }, [calendar, workerId]);

  const summary = people.reduce((sum, row) => ({
    hours: sum.hours + row.basic_hours,
    base: sum.base + row.base_pay,
    holiday: sum.holiday + row.weekly_holiday_pay,
    total: sum.total + row.total_pay,
  }), { hours: 0, base: 0, holiday: 0, total: 0 });

  if (allowed === null) return <Loading text="불러오는 중..." />;
  if (!allowed) {
    return (
      <div>
        <PageHeader title="비용 통계" subtitle="아르바이트" />
        <Alert type="error" message="아르바이트 관리 권한이 필요합니다." />
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="비용 통계" subtitle="사람별, 날짜별 근무 비용입니다." />
      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}
      <Card style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'end' }}>
          <Button type="button" variant="secondary" onClick={() => shiftMonth(-1)}>이전 달</Button>
          <strong>{year}년 {month}월</strong>
          <Button type="button" variant="secondary" onClick={() => shiftMonth(1)}>다음 달</Button>
          <label className="ops-label">
            알바
            <select className="ui-control" value={workerId} onChange={(event) => setWorkerId(Number(event.target.value))}>
              <option value={0}>전체</option>
              {(calendar?.workers || []).map((worker) => (
                <option key={worker.id} value={worker.id}>{worker.name}{worker.active ? '' : ' (그만둠)'}</option>
              ))}
            </select>
          </label>
        </div>
      </Card>

      {loading || !calendar ? <Loading text="불러오는 중..." /> : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.5rem', marginBottom: '1rem' }}>
            {[
              ['인원', `${people.length}명`],
              ['근무시간', `${hoursText(summary.hours)}시간`],
              ['근무수당', won(summary.base)],
              ['주휴수당', won(summary.holiday)],
              ['합계', won(summary.total)],
            ].map(([label, value]) => (
              <div key={label} style={{ background: '#f8f9fc', borderRadius: 8, padding: '0.7rem 0.8rem' }}>
                <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>{label}</div>
                <div style={{ fontWeight: 700 }}>{value}</div>
              </div>
            ))}
          </div>

          <Card title="개인별 총계" style={{ marginBottom: '1rem' }}>
            {people.length === 0 ? <p style={{ margin: 0, color: '#6b7280' }}>이 조건의 근무가 없습니다.</p> : (
              <div style={{ overflowX: 'auto' }}>
                <table>
                  <thead>
                    <tr>{['이름', '시급', '근무시간', '근무수당', '주휴시간', '주휴수당', '합계'].map((head) => <th key={head}>{head}</th>)}</tr>
                  </thead>
                  <tbody>
                    {people.map((row) => (
                      <tr key={row.worker_id}>
                        <td>{row.name}</td>
                        <td>{won(row.hourly_wage)}</td>
                        <td>{hoursText(row.basic_hours)}</td>
                        <td>{won(row.base_pay)}</td>
                        <td>{hoursText(row.weekly_holiday_hours)}</td>
                        <td>{won(row.weekly_holiday_pay)}</td>
                        <td>{won(row.total_pay)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card title="일별 총계">
            {days.length === 0 ? <p style={{ margin: 0, color: '#6b7280' }}>이 조건의 근무가 없습니다.</p> : (
              <div style={{ overflowX: 'auto' }}>
                <table>
                  <thead>
                    <tr>{['날짜', '인원', '일한 사람', '근무시간', '근무수당', '주휴수당', '합계'].map((head) => <th key={head}>{head}</th>)}</tr>
                  </thead>
                  <tbody>
                    {days.map((row) => (
                      <tr key={row.date}>
                        <td>{row.label}</td>
                        <td>{row.headcount}</td>
                        <td>{row.names.join(', ') || '-'}</td>
                        <td>{hoursText(row.hours)}</td>
                        <td>{won(row.workPay)}</td>
                        <td>{won(row.holidayPay)}</td>
                        <td>{won(row.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
