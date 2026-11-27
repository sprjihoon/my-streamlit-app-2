'use client';

import { useCallback, useEffect, useState } from 'react';
import { Alert } from '@/components/Alert';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import PageHeader from '@/components/ui/page-header';
import { Button } from '@/components/ui/button';
import { API, apiError, canManagePartTime, downloadPartTimeExcel, downloadPartTimeSlipPdf, hoursText, won } from '../model';
import { PartTimeSlipPrint } from './slip-print';

interface SlipLine {
  work_date: string;
  hours: number;
  start_time?: string;
  end_time?: string;
  shift_label?: string;
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
  withholding_kind: string;
  pay_regime?: string;
  company_cost?: number;
  income_tax: number;
  local_tax: number;
  employment_insurance: number;
  pension: number;
  pension_base: number;
  health: number;
  care: number;
  deduction_total: number;
  net_pay: number;
  employer_employment: number;
  employer_pension: number;
  employer_health: number;
  employer_care: number;
  employer_industrial: number;
  employer_total: number;
  insurance_note: string;
  lines: SlipLine[];
}

function regimeLabel(kind: string | undefined) {
  if (kind === 'short') return '단기 · 주 15시간 미만';
  if (kind === 'short_long') return '장기 · 주 15시간 미만';
  if (kind === 'daily') return '단기 · 일용근로';
  if (kind === 'regular') return '장기 · 일반근로';
  if (kind === 'business' || kind === 'business_3_3') return '인적용역 3.3%';
  return '근로';
}

export default function PartTimeSlipsPage() {
  const now = new Date();
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [slips, setSlips] = useState<Slip[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [printSlips, setPrintSlips] = useState<Slip[] | null>(null);

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

  const slip = slips.find((item) => item.worker_id === selected) || null;

  if (allowed === null) return <Loading text="불러오는 중..." />;
  if (!allowed) {
    return (
      <div>
        <PageHeader title="급여명세서" subtitle="아르바이트" />
        <Alert type="error" message="아르바이트 관리 권한이 필요합니다." />
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="급여명세서" subtitle="알바에게 줄 금액은 총지급에서 원천세와 근로자 보험료를 뺀 금액입니다. 산재와 회사 부담 보험료는 급여에서 빼지 않습니다." />
      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}
      <Card style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <Button type="button" variant="secondary" onClick={() => shiftMonth(-1)}>이전 달</Button>
          <strong>{year}년 {month}월</strong>
          <Button type="button" variant="secondary" onClick={() => shiftMonth(1)}>다음 달</Button>
          <Button type="button" variant="secondary" disabled={!slip} onClick={() => slip && setPrintSlips([slip])}>이 사람 출력</Button>
          <Button type="button" variant="primary" disabled={!slip} onClick={async () => {
            if (!slip) return;
            setError(null);
            try {
              await downloadPartTimeSlipPdf(year, month, { id: slip.worker_id, name: slip.name });
            } catch (caught) {
              setError(caught instanceof Error ? caught.message : 'PDF를 받지 못했습니다.');
            }
          }}>이 사람 PDF</Button>
          <Button type="button" variant="secondary" disabled={slips.length === 0} onClick={() => setPrintSlips(slips)}>이 달 전체 출력</Button>
          <Button type="button" variant="primary" disabled={slips.length === 0} onClick={async () => {
            setError(null);
            try {
              await downloadPartTimeSlipPdf(year, month);
            } catch (caught) {
              setError(caught instanceof Error ? caught.message : 'PDF를 받지 못했습니다.');
            }
          }}>이 달 전체 PDF</Button>
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
                  <span style={{ marginLeft: 6, color: '#6b7280', fontSize: '0.8rem' }}>{regimeLabel(item.pay_regime)}</span>
                  <div style={{ fontSize: '0.8rem', marginTop: 2 }}>지급 {won(item.net_pay)}</div>
                </button>
              ))}
            </div>
          </Card>
          {slip && (
            <Card title={`${slip.name} ${year}년 ${month}월`}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.5rem', marginBottom: '1rem' }}>
                {[
                  ['적용', regimeLabel(slip.pay_regime)],
                  ['시급', won(slip.hourly_wage)],
                  ['근로일수', `${slip.work_days}일`],
                  ['일평균 근로시간', `${hoursText(slip.average_hours)}시간`],
                  ['총지급액', won(slip.taxable_pay + slip.nontaxable_pay)],
                  ['알바에게 줄 금액', won(slip.net_pay)],
                  ['회사 총비용', won(slip.company_cost || slip.taxable_pay + slip.employer_total)],
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
                    <tr>{['알바 급여에서 빼는 금액', '내용', '금액'].map((head) => <th key={head}>{head}</th>)}</tr>
                  </thead>
                  <tbody>
                    {slip.withholding_kind === 'business_3_3' ? (
                      <>
                        <tr><td>소득세</td><td>지급액의 3%. 10원 미만은 버리고, 1,000원 미만이어도 뗍니다.</td><td>{won(slip.income_tax)}</td></tr>
                        <tr><td>지방소득세</td><td>소득세의 10%. 합쳐 3.3%입니다.</td><td>{won(slip.local_tax)}</td></tr>
                      </>
                    ) : (
                      <>
                        {slip.withholding_kind === 'daily' && (
                          <tr><td>근로소득공제</td><td>15만 원 × 근로일수. 세금 계산용이며 급여에서 빼지 않습니다.</td><td>{won(slip.earned_income_deduction)}</td></tr>
                        )}
                        <tr><td>소득세</td><td>{slip.withholding_kind === 'daily' ? '일용근로소득입니다.' : '이 금액대 근로소득세는 0원입니다.'}</td><td>{won(slip.income_tax)}</td></tr>
                        <tr><td>지방소득세</td><td>소득세의 10%</td><td>{won(slip.local_tax)}</td></tr>
                        <tr><td>고용보험</td><td>과세소득의 0.9%. 해당 없으면 0원입니다.</td><td>{won(slip.employment_insurance)}</td></tr>
                        <tr><td>국민연금</td><td>기준소득월액 {won(slip.pension_base)}의 4.75%</td><td>{won(slip.pension)}</td></tr>
                        <tr><td>건강보험</td><td>과세소득의 3.595%</td><td>{won(slip.health)}</td></tr>
                        <tr><td>장기요양</td><td>건강보험료의 13.14%</td><td>{won(slip.care)}</td></tr>
                      </>
                    )}
                    <tr><td>공제합계</td><td>알바에게 주지 않고 회사가 납부할 금액</td><td>{won(slip.deduction_total)}</td></tr>
                    <tr><td>알바에게 줄 금액</td><td>총지급액에서 공제합계를 뺀 금액</td><td>{won(slip.net_pay)}</td></tr>
                  </tbody>
                </table>
              </div>
              <p style={{ margin: '0 0 1rem', color: '#6b7280', fontSize: '0.85rem' }}>{slip.insurance_note} 산재보험은 회사만 냅니다.</p>
              {slip.withholding_kind !== 'business_3_3' && (
                <div style={{ overflowX: 'auto', marginBottom: '1rem' }}>
                  <table>
                    <thead>
                      <tr>{['회사가 따로 내는 보험', '내용', '금액'].map((head) => <th key={head}>{head}</th>)}</tr>
                    </thead>
                    <tbody>
                      <tr><td>고용보험</td><td>실업급여 0.9%와 고용안정 0.25%</td><td>{won(slip.employer_employment)}</td></tr>
                      <tr><td>국민연금</td><td>근로자와 같은 금액</td><td>{won(slip.employer_pension)}</td></tr>
                      <tr><td>건강보험</td><td>근로자와 같은 금액</td><td>{won(slip.employer_health)}</td></tr>
                      <tr><td>장기요양</td><td>근로자와 같은 금액</td><td>{won(slip.employer_care)}</td></tr>
                      <tr><td>산재보험</td><td>과세소득의 0.8%. 급여에서 빼지 않습니다.</td><td>{won(slip.employer_industrial)}</td></tr>
                      <tr><td>회사 부담 합계</td><td>알바에게 줄 금액과 별도로 회사가 냅니다.</td><td>{won(slip.employer_total)}</td></tr>
                    </tbody>
                  </table>
                </div>
              )}
              <div style={{ overflowX: 'auto' }}>
                <table>
                  <thead>
                    <tr>{['근무일', '시작', '마감', '시간', '근무수당'].map((head) => <th key={head}>{head}</th>)}</tr>
                  </thead>
                  <tbody>
                    {slip.lines.map((line) => (
                      <tr key={line.work_date}>
                        <td>{line.work_date}</td>
                        <td>{line.start_time || '—'}</td>
                        <td>{line.shift_label?.includes('익일') ? `익일 ${line.end_time}` : (line.end_time || '—')}</td>
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
      {printSlips && (
        <PartTimeSlipPrint slips={printSlips} year={year} month={month} onClose={() => setPrintSlips(null)} />
      )}
    </div>
  );
}
