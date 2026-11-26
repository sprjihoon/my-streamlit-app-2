'use client';

import { useCallback, useEffect, useState } from 'react';
import { Alert } from '@/components/Alert';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import { useYesNo } from '@/components/YesNoDialog';
import PageHeader from '@/components/ui/page-header';
import { Button } from '@/components/ui/button';
import { A4Preview } from './a4-preview';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface EmployeeRow {
  user_id: number;
  nickname: string;
  department: string;
  position: string;
  join_date: string;
  state: 'new' | 'draft';
  draft_id: number | null;
  employee_name: string;
  updated_at: string | null;
}

interface StoredContract {
  id: number;
  user_id: number;
  employee_name: string;
  completed_at: string;
  net_pay: number;
  gross_pay: number;
  department: string;
  nickname: string;
  can_reactivate: boolean;
}

interface ContractForm {
  employee_name: string;
  job_title: string;
  rank_title: string;
  resident_id: string;
  address: string;
  phone: string;
  hire_date: string;
  contract_start: string;
  contract_end: string;
  base_hours: number;
  overtime_hours: number;
  holiday_hours: number;
  night_hours: number;
  net_pay: number;
  vehicle_allowance: number;
  meal_allowance: number;
  position_allowance: number;
  income_tax: number;
  weekday_hours: string;
  break_time: string;
  work_days: string;
  pay_day: number;
}

interface PayCalc {
  taxable: number;
  gross: number;
  net: number;
  annual: number;
  deduction_total: number;
  pension: number;
  health: number;
  care: number;
  income_tax: number;
  local_tax: number;
  employment: number;
  hourly: number;
  base_pay: number;
  overtime_pay: number;
  holiday_pay: number;
  night_pay: number;
  meal_allowance: number;
  vehicle_allowance: number;
  position_allowance: number;
}

const EMPTY_FORM: ContractForm = {
  employee_name: '',
  job_title: '',
  rank_title: '',
  resident_id: '',
  address: '',
  phone: '',
  hire_date: '',
  contract_start: '',
  contract_end: '',
  base_hours: 209,
  overtime_hours: 0,
  holiday_hours: 0,
  night_hours: 0,
  net_pay: 0,
  vehicle_allowance: 0,
  meal_allowance: 0,
  position_allowance: 0,
  income_tax: 0,
  weekday_hours: '09:00~18:00',
  break_time: '1시간 (12~13)',
  work_days: '주중 평균 5일 근무',
  pay_day: 15,
};

function won(value: number) {
  return `${Math.round(value || 0).toLocaleString('ko-KR')}원`;
}

async function apiError(res: Response) {
  const text = await res.text();
  try {
    const data = JSON.parse(text);
    if (typeof data?.detail === 'string') return data.detail;
  } catch {
    /* 본문이 JSON이 아니면 그대로 보여 준다 */
  }
  return text || '요청에 실패했습니다.';
}

export default function EmploymentContractsPage() {
  const { ask, dialog } = useYesNo();
  const [view, setView] = useState<'open' | 'completed'>('open');
  const [employees, setEmployees] = useState<EmployeeRow[]>([]);
  const [stored, setStored] = useState<StoredContract[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [printedId, setPrintedId] = useState<number | null>(null);
  const [isAdmin, setIsAdmin] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<ContractForm>(EMPTY_FORM);
  const [calc, setCalc] = useState<PayCalc | null>(null);
  const [sheets, setSheets] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (nextView: 'open' | 'completed') => {
    const token = localStorage.getItem('token') || '';
    setLoading(true);
    setError(null);
    const res = await fetch(`${API}/employment-contracts?token=${encodeURIComponent(token)}&view=${nextView}`);
    if (!res.ok) {
      setError(await apiError(res));
      setLoading(false);
      return;
    }
    const data = await res.json();
    if (nextView === 'open') setEmployees(data.employees || []);
    else setStored(data.contracts || []);
    setLoading(false);
  }, []);

  useEffect(() => {
    try {
      const user = JSON.parse(localStorage.getItem('user') || '{}');
      setIsAdmin(!!user.is_admin);
    } catch {
      setIsAdmin(false);
    }
    load('open');
  }, [load]);

  function patch<K extends keyof ContractForm>(key: K, value: ContractForm[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function openEditor(userId: number) {
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    setSuccess(null);
    setPrintedId(null);
    const res = await fetch(`${API}/employment-contracts/users/${userId}?token=${encodeURIComponent(token)}`);
    setBusy(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    const data = await res.json();
    setEditingId(userId);
    setForm({ ...EMPTY_FORM, ...data.input });
    setCalc(data.calc);
    setView('open');
  }

  async function preview() {
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    const res = await fetch(`${API}/employment-contracts/preview?token=${encodeURIComponent(token)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    });
    setBusy(false);
    if (!res.ok) {
      setCalc(null);
      setError(await apiError(res));
      return;
    }
    const data = await res.json();
    setCalc(data.calc);
  }

  async function openA4Preview() {
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    const res = await fetch(`${API}/employment-contracts/preview-pages?token=${encodeURIComponent(token)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    });
    setBusy(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    const data = await res.json();
    setSheets(data.pages || []);
  }

  async function saveDraft() {
    if (!editingId) return;
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    const res = await fetch(`${API}/employment-contracts/users/${editingId}?token=${encodeURIComponent(token)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    });
    setBusy(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    const data = await res.json();
    setCalc(data.calc);
    setSuccess('작성 중인 내용을 저장했습니다.');
    load('open');
  }

  async function complete() {
    if (!editingId) return;
    const ok = await ask('회사 직인을 찍어 근로계약서를 날인합니다.\n날인하면 이 직원은 작성 목록에서 숨겨지고 PDF로 보관됩니다.\n진행할까요?');
    if (!ok) return;
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    const res = await fetch(`${API}/employment-contracts/users/${editingId}/complete?token=${encodeURIComponent(token)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    });
    setBusy(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    const data = await res.json();
    setEditingId(null);
    setCalc(null);
    setPrintedId(data.id);
    setSuccess(`${form.employee_name} 근로계약서에 날인했습니다.`);
    setView('open');
    load('open');
  }

  async function reactivate(row: StoredContract) {
    const ok = await ask(`${row.employee_name} 님을 작성 목록에 다시 표시합니다.\n기존 PDF는 그대로 남습니다.\n진행할까요?`);
    if (!ok) return;
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    const res = await fetch(`${API}/employment-contracts/users/${row.user_id}/reactivate?token=${encodeURIComponent(token)}`, {
      method: 'POST',
    });
    setBusy(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    setSuccess(`${row.employee_name} 님을 다시 작성할 수 있습니다.`);
    setView('open');
    await load('open');
    openEditor(row.user_id);
  }

  function changeView(next: 'open' | 'completed') {
    setView(next);
    setEditingId(null);
    load(next);
  }

  if (!isAdmin) {
    return (
      <div>
        <PageHeader title="근로계약" subtitle="직원관리" />
        <Alert type="error" message="관리자만 근로계약서를 다룰 수 있습니다." />
      </div>
    );
  }

  return (
    <div>
      {dialog}
      {sheets && <A4Preview pages={sheets} overlay onClose={() => setSheets(null)} />}
      <PageHeader
        title="근로계약"
        subtitle="계약 내용을 입력하고 날인하면 회사 직인이 찍힌 PDF가 보관됩니다. 날인한 직원은 작성 목록에서 빠집니다."
      />
      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}
      {success && (
        <Alert
          type="success"
          message={printedId ? `${success} 출력은 완료 보관의 PDF에서 할 수 있습니다.` : success}
          onClose={() => { setSuccess(null); setPrintedId(null); }}
        />
      )}
      {printedId && (
        <div style={{ marginBottom: '1rem' }}>
          <a href={`/employment-contracts/print/${printedId}`} target="_blank" rel="noreferrer">방금 보관한 계약서 열기</a>
        </div>
      )}

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        <Button type="button" variant={view === 'open' ? 'primary' : 'secondary'} onClick={() => changeView('open')}>작성 대상</Button>
        <Button type="button" variant={view === 'completed' ? 'primary' : 'secondary'} onClick={() => changeView('completed')}>완료 보관</Button>
      </div>

      {editingId && view === 'open' && (
        <Card style={{ marginBottom: '1.25rem' }}>
          <h3 style={{ marginTop: 0 }}>계약 작성</h3>
          <p style={{ color: '#6b7280', fontSize: '0.85rem' }}>
            차량지원과 식대는 비과세라 보험료 기준에서 빠집니다. 직책수당은 월급 안에서 기본급과 나눠 표시하며, 맞추는 금액은 실수령액입니다. 회사명과 대표, 주소는 회사 설정을 사용합니다.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem' }}>
            <Field label="성명" value={form.employee_name} onChange={(value) => patch('employee_name', value)} />
            <Field label="주민등록번호" value={form.resident_id} onChange={(value) => patch('resident_id', value)} />
            <Field label="직무" value={form.job_title} onChange={(value) => patch('job_title', value)} />
            <Field label="직급" value={form.rank_title} onChange={(value) => patch('rank_title', value)} />
            <Field label="주소" value={form.address} onChange={(value) => patch('address', value)} />
            <Field label="연락처" value={form.phone} onChange={(value) => patch('phone', value)} />
            <Field label="입사일" type="date" value={form.hire_date} onChange={(value) => patch('hire_date', value)} />
            <Field label="계약 시작" type="date" value={form.contract_start} onChange={(value) => patch('contract_start', value)} />
            <Field label="계약 종료" type="date" value={form.contract_end} onChange={(value) => patch('contract_end', value)} />
            <Field label="평일 근로시간" value={form.weekday_hours} onChange={(value) => patch('weekday_hours', value)} />
            <Field label="휴게시간" value={form.break_time} onChange={(value) => patch('break_time', value)} />
            <Field label="근로일" value={form.work_days} onChange={(value) => patch('work_days', value)} />
            <Field label="급여일" type="number" value={String(form.pay_day)} onChange={(value) => patch('pay_day', Number(value) || 0)} />
            <Field label="실수령액" type="number" value={String(form.net_pay)} onChange={(value) => patch('net_pay', Number(value) || 0)} />
            <Field label="차량지원" type="number" value={String(form.vehicle_allowance)} onChange={(value) => patch('vehicle_allowance', Number(value) || 0)} />
            <Field label="식대" type="number" value={String(form.meal_allowance)} onChange={(value) => patch('meal_allowance', Number(value) || 0)} />
            <Field label="직책수당" type="number" value={String(form.position_allowance)} onChange={(value) => patch('position_allowance', Number(value) || 0)} />
            <Field label="소득세" type="number" value={String(form.income_tax)} onChange={(value) => patch('income_tax', Number(value) || 0)} />
            <Field label="기본근로시간" type="number" value={String(form.base_hours)} onChange={(value) => patch('base_hours', Number(value) || 0)} />
            <Field label="초과근로시간" type="number" value={String(form.overtime_hours)} onChange={(value) => patch('overtime_hours', Number(value) || 0)} />
            <Field label="휴일근로시간" type="number" value={String(form.holiday_hours)} onChange={(value) => patch('holiday_hours', Number(value) || 0)} />
            <Field label="야간근로시간" type="number" value={String(form.night_hours)} onChange={(value) => patch('night_hours', Number(value) || 0)} />
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem', flexWrap: 'wrap' }}>
            <Button type="button" variant="secondary" disabled={busy} onClick={preview}>급여 계산</Button>
            <Button type="button" variant="secondary" disabled={busy} onClick={openA4Preview}>A4 미리보기</Button>
            <Button type="button" variant="secondary" disabled={busy} onClick={saveDraft}>임시 저장</Button>
            <Button type="button" variant="success" disabled={busy} onClick={complete}>날인</Button>
            <Button type="button" variant="ghost" disabled={busy} onClick={() => setEditingId(null)}>닫기</Button>
          </div>
          {calc && (
            <div style={{ marginTop: '1rem', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.5rem' }}>
              {[
                ['월급여', calc.gross],
                ['실수령액', calc.net],
                ['총연봉', calc.annual],
                ['공제합계', calc.deduction_total],
                ['기본급', calc.base_pay],
                ['통상시급', calc.hourly],
                ['연장수당', calc.overtime_pay],
                ['휴일수당', calc.holiday_pay],
                ['야간수당', calc.night_pay],
                ['국민연금', calc.pension],
                ['건강보험', calc.health],
                ['장기요양', calc.care],
                ['고용보험', calc.employment],
              ].map(([label, value]) => (
                <div key={String(label)} style={{ background: '#f8f9fc', borderRadius: 8, padding: '0.55rem 0.7rem' }}>
                  <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>{label}</div>
                  <div style={{ fontWeight: 700 }}>{won(Number(value))}</div>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {loading ? <Loading text="불러오는 중..." /> : view === 'open' ? (
        <Card>
          <table>
            <thead>
              <tr>
                {['성함', '팀', '직급', '입사일', '상태', ''].map((head) => <th key={head}>{head}</th>)}
              </tr>
            </thead>
            <tbody>
              {employees.length === 0 && (
                <tr><td colSpan={6} style={{ color: '#6b7280' }}>작성할 직원이 없습니다. 완료한 계약은 완료 보관에 있습니다.</td></tr>
              )}
              {employees.map((row) => (
                <tr key={row.user_id}>
                  <td>{row.nickname}</td>
                  <td>{row.department || '—'}</td>
                  <td>{row.position || '—'}</td>
                  <td>{row.join_date || '—'}</td>
                  <td>{row.state === 'draft' ? '작성 중' : '미작성'}</td>
                  <td>
                    <Button type="button" variant="primary" disabled={busy} onClick={() => openEditor(row.user_id)}>
                      {row.state === 'draft' ? '이어서 작성' : '작성'}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ) : (
        <Card>
          <table>
            <thead>
              <tr>
                {['성명', '팀', '완료일', '실수령액', '월급여', ''].map((head) => <th key={head}>{head}</th>)}
              </tr>
            </thead>
            <tbody>
              {stored.length === 0 && (
                <tr><td colSpan={6} style={{ color: '#6b7280' }}>보관된 계약서가 없습니다.</td></tr>
              )}
              {stored.map((row) => (
                <tr key={row.id}>
                  <td>{row.employee_name}</td>
                  <td>{row.department || '—'}</td>
                  <td>{row.completed_at || '—'}</td>
                  <td>{won(row.net_pay)}</td>
                  <td>{won(row.gross_pay)}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <a href={`/employment-contracts/print/${row.id}`} target="_blank" rel="noreferrer">출력</a>
                    {row.can_reactivate && (
                      <Button type="button" variant="secondary" style={{ marginLeft: 8 }} disabled={busy} onClick={() => reactivate(row)}>
                        다시 활성화
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = 'text',
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
}) {
  return (
    <label>
      <span className="ops-label">{label}</span>
      <input
        className="ui-control"
        type={type}
        value={value}
        autoComplete="off"
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
