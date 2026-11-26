'use client';

import { useCallback, useEffect, useState } from 'react';
import { Alert } from '@/components/Alert';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import { useYesNo } from '@/components/YesNoDialog';
import PageHeader from '@/components/ui/page-header';
import { Button } from '@/components/ui/button';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface PayrollLine {
  seq: number;
  employee_name: string;
  affiliation: string;
  hire_date: string;
  resident_id: string;
  base_pay: number;
  overtime_pay: number;
  holiday_pay: number;
  night_pay: number;
  position_allowance: number;
  vehicle_allowance: number;
  meal_allowance: number;
  gross_pay: number;
  income_tax: number;
  local_tax: number;
  pension: number;
  health: number;
  care: number;
  employment: number;
  deduction_total: number;
  net_pay: number;
}

interface Ledger {
  year: number;
  month: number;
  company_name: string;
  period_label: string;
  created_at: string;
  origin?: string;
  lines: PayrollLine[];
  totals: PayrollLine;
  existed?: boolean;
  skipped?: string[];
}

function won(value: number) {
  return `${Number(value || 0).toLocaleString('ko-KR')}원`;
}

async function apiError(res: Response) {
  try {
    const data = await res.json();
    return data.detail || '요청을 처리하지 못했습니다.';
  } catch {
    return '요청을 처리하지 못했습니다.';
  }
}

export default function PayrollLedgerPage() {
  const { ask, dialog } = useYesNo();
  const now = new Date();
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [ledger, setLedger] = useState<Ledger | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const load = useCallback(async (nextYear: number, nextMonth: number) => {
    const token = localStorage.getItem('token') || '';
    setLoading(true);
    setError(null);
    const res = await fetch(`${API}/payroll-ledgers/${nextYear}/${nextMonth}?token=${encodeURIComponent(token)}`);
    if (res.status === 404) {
      setLedger(null);
      setLoading(false);
      return;
    }
    if (!res.ok) {
      setError(await apiError(res));
      setLoading(false);
      return;
    }
    setLedger(await res.json());
    setLoading(false);
  }, []);

  useEffect(() => {
    let admin = false;
    try {
      admin = !!JSON.parse(localStorage.getItem('user') || '{}').is_admin;
    } catch {
      admin = false;
    }
    setIsAdmin(admin);
    if (admin) load(year, month);
    else setLoading(false);
  }, [load, year, month]);

  async function create(replace: boolean) {
    if (replace) {
      const ok = await ask('이 달 급여대장을 현재 근로계약 급여로 다시 만듭니다.\n이미 만든 내용은 바뀝니다.\n진행할까요?');
      if (!ok) return;
    }
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    setSuccess(null);
    const res = await fetch(`${API}/payroll-ledgers?token=${encodeURIComponent(token)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ year, month, replace }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    const data = await res.json();
    setLedger(data);
    if (data.existed) setSuccess('이미 만든 급여대장을 그대로 보여 줍니다.');
    else setSuccess(`${year}년 ${month}월 급여대장을 근로계약 급여로 만들었습니다.`);
  }

  async function download() {
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    const res = await fetch(`${API}/payroll-ledgers/${year}/${month}/xlsx?token=${encodeURIComponent(token)}`);
    setBusy(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `급여대장-${year}-${String(month).padStart(2, '0')}.xlsx`;
    link.click();
    URL.revokeObjectURL(url);
  }

  if (isAdmin === null) return <Loading text="불러오는 중..." />;
  if (!isAdmin) {
    return (
      <div>
        <PageHeader title="급여대장" subtitle="직원관리" />
        <Alert type="error" message="관리자만 급여대장을 볼 수 있습니다." />
      </div>
    );
  }

  const totals = ledger?.totals;
  return (
    <div>
      {dialog}
      <PageHeader
        title="급여대장"
        subtitle="급여가 입력된 근로계약을 모아 매달 급여대장을 만듭니다. 차량지원과 식대는 비과세입니다."
      />
      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}
      {success && <Alert type="success" message={success} onClose={() => setSuccess(null)} />}
      <Card style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'end' }}>
          <label className="ops-label">
            연도
            <input className="ui-control" type="number" value={year} onChange={(event) => setYear(Number(event.target.value) || year)} />
          </label>
          <label className="ops-label">
            월
            <input className="ui-control" type="number" min={1} max={12} value={month} onChange={(event) => setMonth(Number(event.target.value) || month)} />
          </label>
          <Button type="button" variant="primary" disabled={busy} onClick={() => create(false)}>대장 만들기</Button>
          <Button type="button" variant="secondary" disabled={busy || !ledger} onClick={download}>엑셀 다운로드</Button>
          <Button type="button" variant="secondary" disabled={busy || !ledger} onClick={() => create(true)}>계약에서 다시 만들기</Button>
        </div>
      </Card>
      {loading ? <Loading text="불러오는 중..." /> : !ledger ? (
        <Card><p style={{ margin: 0, color: '#6b7280' }}>이 달 급여대장이 없습니다. 대장 만들기를 누르면 근로계약 급여로 채웁니다.</p></Card>
      ) : (
        <Card>
          <p style={{ marginTop: 0, color: '#374151' }}>
            {ledger.company_name} · {ledger.period_label} · {ledger.lines.length}명
            {ledger.origin === 'excel' ? ' · 급여대장 파일을 그대로 반영했습니다.' : ''}
          </p>
          {!!ledger.skipped?.length && (
            <p style={{ color: '#92400e' }}>급여를 맞추지 못해 뺀 직원: {ledger.skipped.join(', ')}</p>
          )}
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  {['순번', '성명', '소속', '입사일', '기본급', '시간외', '휴일', '야간', '직책', '차량', '식대', '총급여', '소득세', '주민세', '국민연금', '건강보험', '장기요양', '고용보험', '공제합계', '실수령액'].map((head) => (
                    <th key={head}>{head}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ledger.lines.map((line) => (
                  <tr key={line.seq}>
                    <td>{line.seq}</td>
                    <td>{line.employee_name}</td>
                    <td>{line.affiliation || '—'}</td>
                    <td>{line.hire_date || '—'}</td>
                    <td>{won(line.base_pay)}</td>
                    <td>{won(line.overtime_pay)}</td>
                    <td>{won(line.holiday_pay)}</td>
                    <td>{won(line.night_pay)}</td>
                    <td>{won(line.position_allowance)}</td>
                    <td>{won(line.vehicle_allowance)}</td>
                    <td>{won(line.meal_allowance)}</td>
                    <td>{won(line.gross_pay)}</td>
                    <td>{won(line.income_tax)}</td>
                    <td>{won(line.local_tax)}</td>
                    <td>{won(line.pension)}</td>
                    <td>{won(line.health)}</td>
                    <td>{won(line.care)}</td>
                    <td>{won(line.employment)}</td>
                    <td>{won(line.deduction_total)}</td>
                    <td>{won(line.net_pay)}</td>
                  </tr>
                ))}
                {totals && (
                  <tr>
                    <td colSpan={4}>합계</td>
                    <td>{won(totals.base_pay)}</td>
                    <td>{won(totals.overtime_pay)}</td>
                    <td>{won(totals.holiday_pay)}</td>
                    <td>{won(totals.night_pay)}</td>
                    <td>{won(totals.position_allowance)}</td>
                    <td>{won(totals.vehicle_allowance)}</td>
                    <td>{won(totals.meal_allowance)}</td>
                    <td>{won(totals.gross_pay)}</td>
                    <td>{won(totals.income_tax)}</td>
                    <td>{won(totals.local_tax)}</td>
                    <td>{won(totals.pension)}</td>
                    <td>{won(totals.health)}</td>
                    <td>{won(totals.care)}</td>
                    <td>{won(totals.employment)}</td>
                    <td>{won(totals.deduction_total)}</td>
                    <td>{won(totals.net_pay)}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
