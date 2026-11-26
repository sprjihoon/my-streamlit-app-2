'use client';

import { useCallback, useEffect, useState } from 'react';
import { Alert } from '@/components/Alert';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import PageHeader from '@/components/ui/page-header';
import { Button } from '@/components/ui/button';
import { API, apiError, downloadPartTimeExcel, hoursText, readAdmin, won } from '../model';

interface SlipLine {
  work_date: string;
  hours: number;
  pay: number;
}

interface Slip {
  worker_id: number;
  name: string;
  reported: boolean;
  hourly_wage: number;
  work_days: number;
  average_hours: number;
  basic_hours: number;
  base_pay: number;
  weekly_holiday_hours: number;
  weekly_holiday_pay: number;
  taxable_pay: number;
  nontaxable_pay: number;
  earned_income_deduction: number;
  tax_base: number;
  calculated_tax: number;
  tax_credit: number;
  income_tax: number;
  local_tax: number;
  deduction_total: number;
  net_pay: number;
  lines: SlipLine[];
}

export default function PartTimeSlipsPage() {
  const now = new Date();
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [slips, setSlips] = useState<Slip[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (nextYear: number, nextMonth: number) => {
    const token = localStorage.getItem('token') || '';
    setLoading(true);
    setError(null);
    const res = await fetch(`${API}/part-time/slips?token=${encodeURIComponent(token)}&year=${nextYear}&month=${nextMonth}`);
    setLoading(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    const data = await res.json();
    setSlips(data.slips || []);
    setSelected((current) => (data.slips || []).some((item: Slip) => item.worker_id === current) ? current : data.slips?.[0]?.worker_id ?? null);
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

  const slip = slips.find((item) => item.worker_id === selected) || null;

  if (isAdmin === null) return <Loading text="불러오는 중..." />;
  if (!isAdmin) {
    return (
      <div>
        <PageHeader title="급여명세서" subtitle="아르바이트" />
        <Alert type="error" message="관리자만 알바 급여명세서를 볼 수 있습니다." />
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="급여명세서" subtitle="일용근로대장의 총지급액, 비과세, 소득세, 지방소득세와 세액공제를 반영합니다." />
      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}
      <Card style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <Button type="button" variant="secondary" onClick={() => shiftMonth(-1)}>이전 달</Button>
          <strong>{year}년 {month}월</strong>
          <Button type="button" variant="secondary" onClick={() => shiftMonth(1)}>다음 달</Button>
          <Button type="button" variant="secondary" onClick={async () => {
            setError(null);
            try {
              await downloadPartTimeExcel(year, month);
            } catch (caught) {
              setError(caught instanceof Error ? caught.message : '엑셀을 받지 못했습니다.');
            }
          }}>노무사 전달용 엑셀</Button>
        </div>
      </Card>
      {loading ? <Loading text="불러오는 중..." /> : slips.length === 0 ? (
        <Card><p style={{ margin: 0, color: '#6b7280' }}>이 달에 근무 기록이 없습니다.</p></Card>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(240px, 340px) 1fr', gap: '1rem', alignItems: 'start' }}>
          <Card title="알바">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
              {slips.map((item) => (
                <button
                  key={item.worker_id}
                  type="button"
                  onClick={() => setSelected(item.worker_id)}
                  style={{
                    textAlign: 'left', border: '1px solid #e5e7eb', borderRadius: 8, padding: '0.55rem 0.7rem',
                    background: item.worker_id === selected ? '#e7f1ff' : 'white', cursor: 'pointer', font: 'inherit',
                  }}
                >
                  <strong>{item.name}</strong>
                  <span style={{ marginLeft: 6, color: '#6b7280', fontSize: '0.8rem' }}>{item.reported ? '신고' : '미신고'}</span>
                  <div style={{ fontSize: '0.8rem', marginTop: 2 }}>실수령 {won(item.net_pay)}</div>
                </button>
              ))}
            </div>
          </Card>
          {slip && (
            <Card title={`${slip.name} ${year}년 ${month}월`}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.5rem', marginBottom: '1rem' }}>
                {[
                  ['구분', slip.reported ? '신고' : '미신고'],
                  ['시급', won(slip.hourly_wage)],
                  ['근로일수', `${slip.work_days}일`],
                  ['일평균 근로시간', `${hoursText(slip.average_hours)}시간`],
                  ['총지급액', won(slip.taxable_pay + slip.nontaxable_pay)],
                  ['실수령액', won(slip.net_pay)],
                ].map(([label, value]) => (
                  <div key={label} style={{ background: '#f8f9fc', borderRadius: 8, padding: '0.55rem 0.7rem' }}>
                    <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>{label}</div>
                    <div style={{ fontWeight: 700 }}>{value}</div>
                  </div>
                ))}
              </div>
              <div style={{ overflowX: 'auto', marginBottom: '1rem' }}>
                <table>
                  <thead>
                    <tr>{['지급 항목', '금액'].map((head) => <th key={head}>{head}</th>)}</tr>
                  </thead>
                  <tbody>
                    <tr><td>근무수당</td><td>{won(slip.base_pay)}</td></tr>
                    <tr><td>주휴수당</td><td>{won(slip.weekly_holiday_pay)}</td></tr>
                    <tr><td>과세소득</td><td>{won(slip.taxable_pay)}</td></tr>
                    <tr><td>비과세소득</td><td>{won(slip.nontaxable_pay)}</td></tr>
                  </tbody>
                </table>
              </div>
              <div style={{ overflowX: 'auto', marginBottom: '1rem' }}>
                <table>
                  <thead>
                    <tr>{['세액', '내용', '금액'].map((head) => <th key={head}>{head}</th>)}</tr>
                  </thead>
                  <tbody>
                    <tr><td>근로소득공제</td><td>15만 원 × 근로일수</td><td>{won(slip.earned_income_deduction)}</td></tr>
                    <tr><td>과세표준</td><td>과세소득에서 공제액을 뺀 금액</td><td>{won(slip.tax_base)}</td></tr>
                    <tr><td>산출세액</td><td>과세표준의 6%</td><td>{won(slip.calculated_tax)}</td></tr>
                    <tr><td>세액공제</td><td>산출세액의 55%</td><td>{won(slip.tax_credit)}</td></tr>
                    <tr><td>소득세</td><td>1,000원 미만은 없음</td><td>{won(slip.income_tax)}</td></tr>
                    <tr><td>지방소득세</td><td>소득세의 10%</td><td>{won(slip.local_tax)}</td></tr>
                    <tr><td>공제합계</td><td>소득세와 지방소득세</td><td>{won(slip.deduction_total)}</td></tr>
                  </tbody>
                </table>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table>
                  <thead>
                    <tr>{['근무일', '시간', '근무수당'].map((head) => <th key={head}>{head}</th>)}</tr>
                  </thead>
                  <tbody>
                    {slip.lines.map((line) => (
                      <tr key={line.work_date}>
                        <td>{line.work_date}</td>
                        <td>{hoursText(line.hours)}</td>
                        <td>{won(line.pay)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
