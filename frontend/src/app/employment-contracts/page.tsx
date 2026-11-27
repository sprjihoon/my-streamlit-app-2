'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Alert } from '@/components/Alert';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import { useYesNo } from '@/components/YesNoDialog';
import PageHeader from '@/components/ui/page-header';
import { Button } from '@/components/ui/button';
import { A4Preview } from './a4-preview';
import { WorkerSeal } from './worker-seal';

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
  worker_filled?: boolean;
  worker_sealed?: boolean;
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
  resident_id?: string;
  has_pdf?: boolean;
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
  taxable_pay: number;
  annual_pay: number;
  pay_basis: 'net' | 'taxable' | 'annual';
  vehicle_allowance: number;
  meal_allowance: number;
  position_allowance: number;
  income_tax: number;
  pension: number | null;
  dependents: number;
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
  taxable_pay: 0,
  annual_pay: 0,
  pay_basis: 'net',
  vehicle_allowance: 0,
  meal_allowance: 0,
  position_allowance: 0,
  income_tax: 0,
  pension: 0,
  dependents: 1,
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
  const router = useRouter();
  const { ask, dialog } = useYesNo();
  const [view, setView] = useState<'open' | 'completed'>('open');
  const [employees, setEmployees] = useState<EmployeeRow[]>([]);
  const [stored, setStored] = useState<StoredContract[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [onceId, setOnceId] = useState<number | null>(null);
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [myId, setMyId] = useState<number | null>(null);
  const [sealed, setSealed] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<ContractForm>(EMPTY_FORM);
  const [calc, setCalc] = useState<PayCalc | null>(null);
  const [sheets, setSheets] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [markRevision, setMarkRevision] = useState(0);
  const [rrnLocked, setRrnLocked] = useState(false);
  const [renewal, setRenewal] = useState(false);
  const [workerSealed, setWorkerSealed] = useState(false);
  const [needsMine, setNeedsMine] = useState(false);
  const [sealAfterPreview, setSealAfterPreview] = useState<'worker' | 'company' | null>(null);

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

  const loadMine = useCallback(async (userId: number, asAdmin = false) => {
    const token = localStorage.getItem('token') || '';
    setLoading(true);
    setError(null);
    const res = await fetch(`${API}/employment-contracts/users/${userId}?token=${encodeURIComponent(token)}`);
    if (res.status === 400) {
      setSealed(true);
      setNeedsMine(false);
      setLoading(false);
      if (!asAdmin) router.replace('/');
      return;
    }
    if (!res.ok) {
      setError(await apiError(res));
      setLoading(false);
      return;
    }
    const data = await res.json();
    if (data.once?.contract_id) {
      setOnceId(data.once.contract_id);
      setSealed(false);
      setNeedsMine(true);
      setLoading(false);
      return;
    }
    setOnceId(null);
    setForm({ ...EMPTY_FORM, ...data.input });
    setRrnLocked(!!data.rrn_locked);
    setRenewal(!!data.renewal);
    setWorkerSealed(!!data.worker_sealed);
    setSealed(false);
    setNeedsMine(true);
    setLoading(false);
  }, [router]);

  useEffect(() => {
    const token = localStorage.getItem('token') || '';
    let cancelled = false;
    (async () => {
      let admin = false;
      let userId: number | null = null;
      let mine = false;
      try {
        const stored = JSON.parse(localStorage.getItem('user') || '{}');
        admin = !!stored.is_admin;
        userId = stored.user_id ?? null;
        mine = !!stored.needs_contract;
      } catch {
        admin = false;
      }
      try {
        const res = await fetch(`${API}/auth/me?token=${encodeURIComponent(token)}`);
        if (res.ok) {
          const me = await res.json();
          admin = !!me.is_admin;
          userId = me.user_id ?? userId;
          mine = !!me.needs_contract;
          localStorage.setItem('user', JSON.stringify(me));
        }
      } catch {
        /* 저장된 계정으로 진행 */
      }
      if (cancelled) return;
      setIsAdmin(admin);
      setMyId(userId);
      setNeedsMine(mine);
      if (admin) load('open');
      if (userId && (!admin || mine)) loadMine(userId, admin);
      else if (!admin) setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [load, loadMine]);

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
    const next = { ...EMPTY_FORM, ...data.input } as ContractForm;
    const basis = next.pay_basis === 'taxable' || next.pay_basis === 'annual' ? next.pay_basis : 'net';
    setEditingId(userId);
    setForm({
      ...next,
      pay_basis: basis,
      net_pay: basis === 'net' ? next.net_pay : 0,
      taxable_pay: basis === 'taxable' ? next.taxable_pay : 0,
      annual_pay: basis === 'annual' ? next.annual_pay : 0,
    });
    setCalc(data.calc);
    setRrnLocked(!!data.rrn_locked);
    setRenewal(!!data.renewal);
    setWorkerSealed(!!data.worker_sealed);
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

  async function openA4Preview(forSeal = false) {
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    const who = editingId ? `&user_id=${editingId}` : '';
    const res = await fetch(`${API}/employment-contracts/preview-pages?token=${encodeURIComponent(token)}${who}`, {
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
    setSealAfterPreview(forSeal ? 'company' : null);
    setSheets(data.pages || []);
  }

  async function previewRow(userId: number) {
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    const draft = await fetch(`${API}/employment-contracts/users/${userId}?token=${encodeURIComponent(token)}`);
    if (!draft.ok) {
      setBusy(false);
      setError(await apiError(draft));
      return;
    }
    const data = await draft.json();
    const res = await fetch(`${API}/employment-contracts/preview-pages?token=${encodeURIComponent(token)}&user_id=${userId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...EMPTY_FORM, ...data.input }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    const pages = await res.json();
    setSealAfterPreview(null);
    setSheets(pages.pages || []);
  }

  async function previewStored(contractId: number) {
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    const res = await fetch(`${API}/employment-contracts/${contractId}/pages?token=${encodeURIComponent(token)}`);
    setBusy(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    const data = await res.json();
    setSealAfterPreview(null);
    setSheets(data.pages || []);
  }

  async function saveWorker() {
    if (!myId) return;
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    const res = await fetch(`${API}/employment-contracts/users/${myId}/worker?token=${encodeURIComponent(token)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        employee_name: form.employee_name,
        resident_id: form.resident_id,
        address: form.address,
        phone: form.phone,
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    setWorkerSealed(false);
    setSuccess('근로자 기재란을 저장했습니다. 내용을 바꾸면 다시 날인합니다.');
    setMarkRevision((value) => value + 1);
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
    setWorkerSealed(false);
    setSuccess('작성 중인 내용을 저장했습니다. 내용이 바뀌면 근로자가 다시 날인합니다.');
    load('open');
  }

  async function complete() {
    if (!editingId) return;
    await openA4Preview(true);
  }

  async function finishCompanySeal() {
    if (!editingId) return;
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
      closePreview();
      setError(await apiError(res));
      return;
    }
    const data = await res.json();
    closePreview();
    setEditingId(null);
    setCalc(null);
    setSuccess(`${form.employee_name} 근로계약서에 날인했습니다. 지금 한 번 확인하거나 인쇄하세요.`);
    setView('open');
    load('open');
    if (myId && editingId === myId) loadMine(myId, true);
    const preview = await fetch(`${API}/employment-contracts/${data.id}/pages?token=${encodeURIComponent(token)}`);
    if (preview.ok) {
      const shown = await preview.json();
      setSealAfterPreview(null);
      setSheets(shown.pages || []);
    }
  }

  async function reactivate(row: StoredContract) {
    const ok = await ask(`${row.employee_name} 님을 재계약합니다.\n주민번호와 이전 계약 내용을 복사하고, 기존 PDF는 그대로 남습니다.\n연봉·기간을 고친 뒤 다시 날인하세요.\n진행할까요?`);
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
    setSuccess(`${row.employee_name} 님 재계약 초안을 만들었습니다. 연봉과 계약 기간을 고친 뒤 날인하세요.`);
    setView('open');
    await load('open');
    openEditor(row.user_id);
  }

  function changeView(next: 'open' | 'completed') {
    setView(next);
    setEditingId(null);
    load(next);
  }

  if (isAdmin === null) {
    return <Loading text="불러오는 중..." />;
  }

  async function previewMine() {
    if (!myId) return;
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    const res = await fetch(`${API}/employment-contracts/users/${myId}/preview-own?token=${encodeURIComponent(token)}`, {
      method: 'POST',
    });
    setBusy(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    const data = await res.json();
    setSealAfterPreview(null);
    setSheets(data.pages || []);
  }

  function closePreview() {
    const consumed = !isAdmin && onceId !== null && sheets !== null;
    setSheets(null);
    setSealAfterPreview(null);
    if (consumed) {
      setOnceId(null);
      router.replace('/');
    }
  }

  async function openOnce() {
    if (!onceId) return;
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    const res = await fetch(`${API}/employment-contracts/${onceId}/pages?token=${encodeURIComponent(token)}`);
    setBusy(false);
    if (!res.ok) {
      setOnceId(null);
      setError(await apiError(res));
      return;
    }
    const data = await res.json();
    setSealAfterPreview(null);
    setSheets(data.pages || []);
  }

  async function confirmPreviewSeal() {
    if (sealAfterPreview === 'worker') await finishWorkerSeal();
    else if (sealAfterPreview === 'company') await finishCompanySeal();
  }

  async function sealMine() {
    if (!myId) return;
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    const saved = await fetch(`${API}/employment-contracts/users/${myId}/worker?token=${encodeURIComponent(token)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        employee_name: form.employee_name,
        resident_id: form.resident_id,
        address: form.address,
        phone: form.phone,
      }),
    });
    if (!saved.ok) {
      setBusy(false);
      setError(await apiError(saved));
      return;
    }
    const preview = await fetch(`${API}/employment-contracts/users/${myId}/preview-own?token=${encodeURIComponent(token)}`, {
      method: 'POST',
    });
    setBusy(false);
    if (!preview.ok) {
      setError(await apiError(preview));
      return;
    }
    const data = await preview.json();
    setSealAfterPreview('worker');
    setSheets(data.pages || []);
  }

  async function finishWorkerSeal() {
    if (!myId) return;
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    const res = await fetch(`${API}/employment-contracts/users/${myId}/worker-seal?token=${encodeURIComponent(token)}`, {
      method: 'POST',
    });
    setBusy(false);
    if (!res.ok) {
      closePreview();
      setWorkerSealed(false);
      setError(await apiError(res));
      return;
    }
    closePreview();
    setWorkerSealed(true);
    setMarkRevision((value) => value + 1);
    setSuccess('계약서를 확인하고 날인했습니다. 회사에서 날인하면 계약이 보관됩니다.');
  }

  const showOwnWorker = Boolean(needsMine && myId && (editingId === null || editingId === myId));

  function ownWorkerBlock() {
    return (
      <>
        {sealed ? (
          <Alert type="info" message="작성할 근로계약이 없습니다." />
        ) : (
          <>
            <Card>
              <h3 style={{ marginTop: 0 }}>{renewal ? '내 계약 · 바뀐 항목만 수정' : '내 근로계약 기재'}</h3>
              <p style={{ marginTop: 0, color: '#1e3a8a', fontSize: '0.85rem' }}>
                관리자라도 본인 계약은 근로자처럼 기재하고 날인한 뒤, 아래에서 회사 날인을 합니다.
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.75rem' }}>
                <Field label="성명" value={form.employee_name} onChange={(value) => patch('employee_name', value)} />
                <Field label="주민등록번호" value={form.resident_id} onChange={(value) => patch('resident_id', value)} locked={rrnLocked} />
                <Field label="주소" value={form.address} onChange={(value) => patch('address', value)} />
                <Field label="연락처" value={form.phone} onChange={(value) => patch('phone', value)} />
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem', flexWrap: 'wrap' }}>
                <Button type="button" variant="secondary" disabled={busy} onClick={saveWorker}>저장</Button>
                <Button type="button" variant="secondary" disabled={busy} onClick={previewMine}>계약서 확인</Button>
                <Button type="button" variant="success" disabled={busy || workerSealed} onClick={sealMine}>계약서 보고 날인</Button>
              </div>
              {workerSealed && (
                <p style={{ marginBottom: 0, color: '#166534' }}>날인했습니다. 내용을 바꾸면 다시 날인합니다. 아래에서 회사 날인을 하면 보관됩니다.</p>
              )}
            </Card>
            {myId && (
              <div style={{ marginTop: '1rem' }}>
                <WorkerSeal userId={myId} name={form.employee_name} revision={markRevision} />
              </div>
            )}
          </>
        )}
      </>
    );
  }

  if (!isAdmin) {
    return (
      <div>
        {dialog}
        {sheets && (
          <A4Preview
            pages={sheets}
            overlay
            onClose={closePreview}
            onConfirm={sealAfterPreview ? confirmPreviewSeal : undefined}
            confirmDisabled={busy}
          />
        )}
        <PageHeader
          title="근로계약"
          subtitle={onceId
            ? '날인 직후 한 번만 확인하거나 인쇄할 수 있습니다. 닫으면 완료 보관은 관리자만 봅니다.'
            : renewal
            ? '이전 계약 내용을 불러왔습니다. 주소·연락처·성함 등 바뀐 항목만 고친 뒤 계약서를 확인하고 날인합니다. 주민번호는 그대로입니다.'
            : '성명과 연락처를 저장하고 도장을 등록한 뒤, 계약서를 확인하고 날인합니다. 급여와 근로조건은 회사에서 적습니다.'}
        />
        {error && <Alert type="error" message={error} onClose={() => setError(null)} />}
        {success && <Alert type="success" message={success} onClose={() => setSuccess(null)} />}
        {loading ? <Loading text="불러오는 중..." /> : onceId ? (
          <Card>
            <h3 style={{ marginTop: 0 }}>날인된 계약서</h3>
            <p>지금 한 번 확인하거나 인쇄할 수 있습니다. 연 뒤에는 완료 보관에서 관리자만 봅니다.</p>
            <Button type="button" variant="success" disabled={busy} onClick={openOnce}>확인하고 인쇄</Button>
          </Card>
        ) : sealed ? (
          <Alert type="info" message="작성할 근로계약이 없습니다." />
        ) : (
          <Card>
            <h3 style={{ marginTop: 0 }}>{renewal ? '바뀐 항목만 수정' : '근로자 기재'}</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.75rem' }}>
              <Field label="성명" value={form.employee_name} onChange={(value) => patch('employee_name', value)} />
              <Field label="주민등록번호" value={form.resident_id} onChange={(value) => patch('resident_id', value)} locked={rrnLocked} />
              <Field label="주소" value={form.address} onChange={(value) => patch('address', value)} />
              <Field label="연락처" value={form.phone} onChange={(value) => patch('phone', value)} />
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem', flexWrap: 'wrap' }}>
              <Button type="button" variant="secondary" disabled={busy} onClick={saveWorker}>저장</Button>
              <Button type="button" variant="secondary" disabled={busy} onClick={previewMine}>계약서 확인</Button>
              <Button type="button" variant="success" disabled={busy || workerSealed} onClick={sealMine}>계약서 보고 날인</Button>
            </div>
            {workerSealed && (
              <p style={{ marginBottom: 0, color: '#166534' }}>날인했습니다. 내용을 바꾸면 다시 날인합니다.</p>
            )}
          </Card>
        )}
        {!loading && !sealed && myId && (
          <div style={{ marginTop: '1rem' }}>
            <WorkerSeal userId={myId} name={form.employee_name} revision={markRevision} />
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      {dialog}
      {sheets && (
        <A4Preview
          pages={sheets}
          overlay
          onClose={closePreview}
          onConfirm={sealAfterPreview ? confirmPreviewSeal : undefined}
          confirmDisabled={busy}
        />
      )}
      <PageHeader
        title="근로계약"
        subtitle="주민번호와 계약 내용은 보관됩니다. 재계약하면 이전 내용을 불러오고, 관리자와 근로자가 바뀐 항목만 고칩니다. 주민번호는 고정입니다."
      />
      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}
      {success && <Alert type="success" message={success} onClose={() => setSuccess(null)} />}
      {showOwnWorker && (
        <div style={{ marginBottom: '1rem' }}>
          {ownWorkerBlock()}
        </div>
      )}

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        <Button type="button" variant={view === 'open' ? 'primary' : 'secondary'} onClick={() => changeView('open')}>작성 대상</Button>
        <Button type="button" variant={view === 'completed' ? 'primary' : 'secondary'} onClick={() => changeView('completed')}>완료 보관</Button>
      </div>

      {editingId && view === 'open' && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="계약 작성"
          style={{ position: 'fixed', inset: 0, zIndex: 70, background: 'rgba(15, 23, 42, 0.45)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '4vh 1rem', overflow: 'auto' }}
          onClick={() => { if (!busy) setEditingId(null); }}
        >
          <div
            style={{ width: 'min(920px, 100%)', background: '#fff', borderRadius: 14, padding: '1.25rem', boxShadow: '0 20px 50px rgba(15, 23, 42, 0.25)' }}
            onClick={(event) => event.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem' }}>
              <h3 style={{ margin: 0 }}>{renewal ? '재계약 작성' : '계약 작성'}</h3>
              <Button type="button" variant="ghost" disabled={busy} onClick={() => setEditingId(null)}>닫기</Button>
            </div>
            <section style={{ marginTop: '1rem', border: '1px solid #bbf7d0', background: '#f0fdf4', borderRadius: 12, padding: '0.9rem' }}>
              <h4 style={{ margin: '0 0 0.35rem' }}>{renewal ? '변동 항목 (관리자도 수정)' : '근로자가 적는 항목'}</h4>
              <p style={{ margin: '0 0 0.75rem', color: '#166534', fontSize: '0.82rem' }}>
                {renewal
                  ? '이전 계약에서 불러왔습니다. 주소·연락처·성함 등 바뀐 내용만 고치면 됩니다. 주민번호는 바꿀 수 없습니다.'
                  : '성명, 주민등록번호, 주소, 연락처는 근로자가 직접 적습니다. 관리자도 같은 칸을 고칠 수 있습니다.'}
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem' }}>
                <Field label="성명" value={form.employee_name} onChange={(value) => patch('employee_name', value)} />
                <Field label="주민등록번호" value={form.resident_id} onChange={(value) => patch('resident_id', value)} locked={rrnLocked} />
                <Field label="주소" value={form.address} onChange={(value) => patch('address', value)} />
                <Field label="연락처" value={form.phone} onChange={(value) => patch('phone', value)} />
              </div>
            </section>
            <section style={{ marginTop: '0.9rem', border: '1px solid #dbeafe', background: '#f8fbff', borderRadius: 12, padding: '0.9rem' }}>
              <h4 style={{ margin: '0 0 0.35rem' }}>내가 적는 항목</h4>
              <p style={{ margin: '0 0 0.75rem', color: '#1e3a8a', fontSize: '0.82rem' }}>
                실수령액, 세전금액, 연봉 중 하나만 적으면 국민연금·건강보험·고용보험·소득세는 자동입니다. 소득세는 간이세액표와 공제대상 가족 수를 씁니다. 근로시간 문구는 지금 쓰는 09:00~18:00, 휴게 1시간, 주 5일을 기본으로 둡니다.
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem' }}>
                <Field label="직무" value={form.job_title} onChange={(value) => patch('job_title', value)} />
                <Field label="직급" value={form.rank_title} onChange={(value) => patch('rank_title', value)} />
                <Field label="입사일" type="date" value={form.hire_date} onChange={(value) => patch('hire_date', value)} />
                <Field label="계약 시작" type="date" value={form.contract_start} onChange={(value) => patch('contract_start', value)} />
                <Field label="계약 종료 (없으면 비움)" type="date" value={form.contract_end} onChange={(value) => patch('contract_end', value)} />
                <Field label="평일 근로시간" value={form.weekday_hours} onChange={(value) => patch('weekday_hours', value)} />
                <Field label="휴게시간" value={form.break_time} onChange={(value) => patch('break_time', value)} />
                <Field label="근로일" value={form.work_days} onChange={(value) => patch('work_days', value)} />
                <Field label="급여일" type="number" value={String(form.pay_day)} onChange={(value) => patch('pay_day', Number(value) || 0)} />
                <label className="ops-label">
                  급여 기준
                  <select
                    className="ui-control"
                    value={form.pay_basis}
                    onChange={(event) => {
                      const next = event.target.value as ContractForm['pay_basis'];
                      setForm((current) => ({
                        ...current,
                        pay_basis: next,
                        net_pay: next === 'net' ? current.net_pay : 0,
                        taxable_pay: next === 'taxable' ? current.taxable_pay : 0,
                        annual_pay: next === 'annual' ? current.annual_pay : 0,
                      }));
                    }}
                  >
                    <option value="net">실수령액</option>
                    <option value="taxable">세전금액</option>
                    <option value="annual">연봉</option>
                  </select>
                </label>
                {form.pay_basis === 'net' && (
                  <Field label="실수령액" type="number" value={String(form.net_pay)} onChange={(value) => patch('net_pay', Number(value) || 0)} />
                )}
                {form.pay_basis === 'taxable' && (
                  <Field label="세전금액" type="number" value={String(form.taxable_pay)} onChange={(value) => patch('taxable_pay', Number(value) || 0)} />
                )}
                {form.pay_basis === 'annual' && (
                  <Field label="연봉" type="number" value={String(form.annual_pay)} onChange={(value) => patch('annual_pay', Number(value) || 0)} />
                )}
                <Field label="차량지원" type="number" value={String(form.vehicle_allowance)} onChange={(value) => patch('vehicle_allowance', Number(value) || 0)} />
                <Field label="식대" type="number" value={String(form.meal_allowance)} onChange={(value) => patch('meal_allowance', Number(value) || 0)} />
                <Field label="직책수당" type="number" value={String(form.position_allowance)} onChange={(value) => patch('position_allowance', Number(value) || 0)} />
                <Field label="공제대상 가족 수" type="number" value={String(form.dependents || 1)} onChange={(value) => patch('dependents', Math.min(10, Math.max(1, Number(value) || 1)))} />
                <Field label="기본근로시간" type="number" value={String(form.base_hours)} onChange={(value) => patch('base_hours', Number(value) || 0)} />
                <Field label="초과근로시간" type="number" value={String(form.overtime_hours)} onChange={(value) => patch('overtime_hours', Number(value) || 0)} />
                <Field label="휴일근로시간" type="number" value={String(form.holiday_hours)} onChange={(value) => patch('holiday_hours', Number(value) || 0)} />
                <Field label="야간근로시간" type="number" value={String(form.night_hours)} onChange={(value) => patch('night_hours', Number(value) || 0)} />
              </div>
            </section>
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem', flexWrap: 'wrap' }}>
              <Button type="button" variant="secondary" disabled={busy} onClick={preview}>급여 계산</Button>
              <Button type="button" variant="secondary" disabled={busy} onClick={openA4Preview}>출력 미리보기</Button>
              <Button type="button" variant="secondary" disabled={busy} onClick={saveDraft}>임시 저장</Button>
              <Button type="button" variant="success" disabled={busy || !workerSealed} onClick={complete}>계약서 보고 날인</Button>
            </div>
            <p style={{ margin: '0.7rem 0 0', color: workerSealed ? '#166534' : '#92400e', fontSize: '0.85rem' }}>
              {workerSealed
                ? '근로자가 계약서를 확인하고 날인했습니다.'
                : '근로자가 계약서를 확인하고 날인하기 전에는 회사 날인을 할 수 없습니다.'}
            </p>
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
                  ['소득세', calc.income_tax],
                  ['주민세', calc.local_tax],
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
          </div>
        </div>
      )}

      {loading ? <Loading text="불러오는 중..." /> : view === 'open' ? (
        <Card>
          <table>
            <thead>
              <tr>
                {['성함', '팀', '직급', '입사일', '상태', '근로자 기재', '근로자 날인', ''].map((head) => <th key={head || 'actions'}>{head}</th>)}
              </tr>
            </thead>
            <tbody>
              {employees.length === 0 && (
                <tr><td colSpan={8} style={{ color: '#6b7280' }}>작성할 직원이 없습니다. 완료한 계약은 완료 보관에 있습니다.</td></tr>
              )}
              {employees.map((row) => (
                <tr key={row.user_id}>
                  <td>{row.nickname}</td>
                  <td>{row.department || '—'}</td>
                  <td>{row.position || '—'}</td>
                  <td>{row.join_date || '—'}</td>
                  <td>{row.state === 'draft' ? '작성 중' : '미작성'}</td>
                  <td>{row.worker_filled ? '기재 완료' : '미기재'}</td>
                  <td>{row.worker_sealed ? '날인' : '대기'}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <Button type="button" variant="primary" disabled={busy} onClick={() => openEditor(row.user_id)}>
                      {row.state === 'draft' ? '이어서 작성' : '작성'}
                    </Button>
                    <Button type="button" variant="secondary" style={{ marginLeft: 8 }} disabled={busy} onClick={() => previewRow(row.user_id)}>
                      출력 미리보기
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
                {['성명', '팀', '주민번호', '완료일', '실수령액', '월급여', '파일', ''].map((head) => <th key={head}>{head}</th>)}
              </tr>
            </thead>
            <tbody>
              {stored.length === 0 && (
                <tr><td colSpan={8} style={{ color: '#6b7280' }}>보관된 계약서가 없습니다.</td></tr>
              )}
              {stored.map((row) => (
                <tr key={row.id}>
                  <td>{row.employee_name}</td>
                  <td>{row.department || '—'}</td>
                  <td>{row.resident_id || '—'}</td>
                  <td>{row.completed_at || '—'}</td>
                  <td>{won(row.net_pay)}</td>
                  <td>{won(row.gross_pay)}</td>
                  <td>{row.has_pdf === false ? '없음' : '보관'}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <Button type="button" variant="secondary" disabled={busy || row.has_pdf === false} onClick={() => previewStored(row.id)}>확인</Button>
                    {' '}
                    <a href={`/employment-contracts/print/${row.id}`} target="_blank" rel="noreferrer">출력</a>
                    {' '}
                    <a
                      href={`${API}/employment-contracts/${row.id}/pdf?token=${encodeURIComponent(typeof window === 'undefined' ? '' : localStorage.getItem('token') || '')}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      PDF
                    </a>
                    {row.can_reactivate && (
                      <Button type="button" variant="secondary" style={{ marginLeft: 8 }} disabled={busy} onClick={() => reactivate(row)}>
                        재계약
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
  locked = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  locked?: boolean;
}) {
  return (
    <label>
      <span className="ops-label">{label}{locked ? ' (고정)' : ''}</span>
      <input
        className="ui-control"
        type={type}
        value={value}
        autoComplete="off"
        readOnly={locked}
        disabled={locked}
        style={locked ? { background: '#f3f4f6', color: '#4b5563' } : undefined}
        onChange={(event) => { if (!locked) onChange(event.target.value); }}
      />
    </label>
  );
}
