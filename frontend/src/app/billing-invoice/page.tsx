'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ─── 타입 ────────────────────────────────────────────────────────────
interface BillingInvoice {
  id: string;
  invoice_no: string | null;
  client_name: string;
  invoice_date: string | null;
  due_date: string | null;
  service_month: string | null;
  subject: string | null;
  supply_amount: number;
  vat_amount: number;
  total_amount: number;
  paid_amount: number;
  paid_date: string | null;
  status: string;
  memo: string | null;
  pdf_filename: string | null;
  created_by: string | null;
  created_at: string;
  confirmed: number;
}

interface ParsedItem {
  line_no: number;
  item_name: string;
  quantity: number | null;
  unit_price: number | null;
  amount: number | null;
  memo: string | null;
}

// ─── 유틸 ────────────────────────────────────────────────────────────
const fmt = (n: number | null | undefined) =>
  n == null ? '-' : n.toLocaleString('ko-KR') + '원';

const fmtDt = (s: string | null) => {
  if (!s) return '-';
  return new Date(s).toLocaleDateString('ko-KR');
};

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { bg: string; color: string }> = {
    '미납': { bg: '#fef2f2', color: '#dc2626' },
    '부분납': { bg: '#fff7ed', color: '#ea580c' },
    '완납': { bg: '#f0fdf4', color: '#16a34a' },
  };
  const s = map[status] || { bg: '#f3f4f6', color: '#6b7280' };
  return (
    <span style={{ padding: '2px 8px', borderRadius: 10, fontSize: '0.72rem', fontWeight: 700, background: s.bg, color: s.color }}>
      {status}
    </span>
  );
}

// ─── 납부 처리 모달 ──────────────────────────────────────────────────
function PayModal({ inv, token, onClose, onSaved }: {
  inv: BillingInvoice; token: string;
  onClose: () => void; onSaved: () => void;
}) {
  const [paid, setPaid] = useState(String(inv.paid_amount || ''));
  const [paidDate, setPaidDate] = useState(inv.paid_date || new Date().toISOString().slice(0, 10));
  const [memo, setMemo] = useState(inv.memo || '');
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    await fetch(`${API}/billing-invoice/${inv.id}?token=${token}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paid_amount: Number(paid), paid_date: paidDate, memo }),
    });
    setSaving(false);
    onSaved();
    onClose();
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ background: 'white', borderRadius: 10, padding: '1.5rem', width: 380, boxShadow: '0 8px 32px rgba(0,0,0,0.15)' }}>
        <h4 style={{ marginBottom: '1rem', color: '#1a3c6e' }}>💳 납부 처리 — {inv.client_name}</h4>
        <div style={{ marginBottom: '0.75rem' }}>
          <div style={{ fontSize: '0.78rem', color: '#6b7280', marginBottom: '0.2rem' }}>청구 금액</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 700 }}>{fmt(inv.total_amount)}</div>
        </div>
        {[
          { label: '입금액 (원)', type: 'number', value: paid, onChange: setPaid },
          { label: '입금일', type: 'date', value: paidDate, onChange: setPaidDate },
        ].map(({ label, type, value, onChange }) => (
          <div key={label} style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'block', fontSize: '0.78rem', color: '#6b7280', marginBottom: '0.2rem' }}>{label}</label>
            <input type={type} value={value} onChange={e => onChange(e.target.value)}
              style={{ width: '100%', padding: '0.45rem 0.6rem', border: '1px solid #d1d5db', borderRadius: 6, fontSize: '0.875rem', boxSizing: 'border-box' }} />
          </div>
        ))}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.78rem', color: '#6b7280', marginBottom: '0.2rem' }}>메모</label>
          <input type="text" value={memo} onChange={e => setMemo(e.target.value)}
            style={{ width: '100%', padding: '0.45rem 0.6rem', border: '1px solid #d1d5db', borderRadius: 6, fontSize: '0.875rem', boxSizing: 'border-box' }} />
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={btnGray}>취소</button>
          <button onClick={save} disabled={saving} style={btnBlue}>{saving ? '저장 중...' : '저장'}</button>
        </div>
      </div>
    </div>
  );
}

// ─── 상세 모달 ───────────────────────────────────────────────────────
function DetailModal({ invId, token, onClose }: { invId: string; token: string; onClose: () => void }) {
  const [data, setData] = useState<(BillingInvoice & { items: ParsedItem[] }) | null>(null);

  useEffect(() => {
    fetch(`${API}/billing-invoice/${invId}?token=${token}`)
      .then(r => r.json()).then(setData);
  }, [invId, token]);

  if (!data) return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ background: 'white', borderRadius: 10, padding: '2rem' }}>로딩 중...</div>
    </div>
  );

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 999, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}>
      <div style={{ background: 'white', borderRadius: 12, width: '100%', maxWidth: 760, maxHeight: '90vh', overflow: 'auto', padding: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h3 style={{ margin: 0, color: '#1a3c6e' }}>{data.client_name} — {data.service_month}</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: '1.2rem', cursor: 'pointer' }}>✕</button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginBottom: '1rem', fontSize: '0.85rem' }}>
          {[
            ['문서번호', data.invoice_no || '-'],
            ['청구일', data.invoice_date || '-'],
            ['납기일', data.due_date || '-'],
            ['건명', data.subject || '-'],
            ['공급가액', fmt(data.supply_amount)],
            ['부가세', fmt(data.vat_amount)],
            ['청구합계', fmt(data.total_amount)],
            ['입금액', fmt(data.paid_amount)],
            ['미수금', fmt((data.total_amount || 0) - (data.paid_amount || 0))],
            ['상태', data.status],
          ].map(([label, value]) => (
            <div key={label} style={{ background: '#f9fafb', borderRadius: 6, padding: '0.4rem 0.6rem' }}>
              <div style={{ fontSize: '0.72rem', color: '#9ca3af' }}>{label}</div>
              <div style={{ fontWeight: 600, color: '#111' }}>{value}</div>
            </div>
          ))}
        </div>

        <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#374151', marginBottom: '0.5rem' }}>항목 ({data.items?.length}개)</div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
            <thead>
              <tr style={{ background: '#1a3c6e', color: 'white' }}>
                {['No', '품명', '카테고리', '수량', '단가', '금액', '비고'].map(h => (
                  <th key={h} style={{ padding: '0.4rem 0.6rem', textAlign: 'left', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.items?.map((it, i) => (
                <tr key={i} style={{ background: (it.amount || 0) < 0 ? '#fef2f2' : i % 2 === 0 ? 'white' : '#f9fafb', borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '0.35rem 0.6rem', color: '#9ca3af' }}>{it.line_no}</td>
                  <td style={{ padding: '0.35rem 0.6rem', fontWeight: 500 }}>{it.item_name}</td>
                  <td style={{ padding: '0.35rem 0.6rem' }}><span style={{ background: '#eff6ff', color: '#1d4ed8', padding: '1px 6px', borderRadius: 4, fontSize: '0.7rem' }}>{(it as any).category || '-'}</span></td>
                  <td style={{ padding: '0.35rem 0.6rem', textAlign: 'right' }}>{it.quantity?.toLocaleString() ?? '-'}</td>
                  <td style={{ padding: '0.35rem 0.6rem', textAlign: 'right' }}>{it.unit_price?.toLocaleString() ?? '-'}</td>
                  <td style={{ padding: '0.35rem 0.6rem', textAlign: 'right', fontWeight: 600, color: (it.amount || 0) < 0 ? '#dc2626' : '#111' }}>
                    {it.amount?.toLocaleString() ?? '-'}
                  </td>
                  <td style={{ padding: '0.35rem 0.6rem', color: '#6b7280', maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{it.memo || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ─── 메인 페이지 ─────────────────────────────────────────────────────
export default function BillingInvoicePage() {
  const [token, setToken] = useState('');
  const [isAdmin, setIsAdmin] = useState(false);
  const [invoices, setInvoices] = useState<BillingInvoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState('');
  const [uploadError, setUploadError] = useState('');
  const [uploadProgress, setUploadProgress] = useState<{ current: number; total: number; name: string } | null>(null);
  const [uploadResults, setUploadResults] = useState<{ name: string; ok: boolean; msg: string }[]>([]);
  const [filterYear, setFilterYear] = useState(new Date().getFullYear());
  const [filterMonth, setFilterMonth] = useState(0);
  const [filterClient, setFilterClient] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [payingInv, setPayingInv] = useState<BillingInvoice | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const [activeTab, setActiveTab] = useState<'list' | 'analytics'>('list');
  const [analytics, setAnalytics] = useState<any>(null);
  const [analyticsYear, setAnalyticsYear] = useState(new Date().getFullYear());
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const tok = localStorage.getItem('token') || '';
    const admin = localStorage.getItem('isAdmin') === 'true';
    setToken(tok);
    setIsAdmin(admin);
    if (!admin) { setLoading(false); return; }
    load(tok);
  }, []); // eslint-disable-line

  async function loadAnalytics(tok: string, year: number) {
    setAnalyticsLoading(true);
    try {
      const r = await fetch(`${API}/billing-invoice/analytics/summary?token=${tok}&year=${year}`);
      if (r.ok) setAnalytics(await r.json());
    } catch { /* silent */ }
    setAnalyticsLoading(false);
  }

  useEffect(() => {
    if (activeTab === 'analytics' && token && isAdmin) loadAnalytics(token, analyticsYear);
  }, [activeTab, analyticsYear, token, isAdmin]); // eslint-disable-line

  const load = useCallback(async (tok: string) => {
    setLoading(true);
    try {
      let url = `${API}/billing-invoice/list?token=${tok}&year=${filterYear}`;
      if (filterMonth) url += `&month=${filterMonth}`;
      if (filterClient) url += `&client_name=${encodeURIComponent(filterClient)}`;
      if (filterStatus) url += `&status=${filterStatus}`;
      const r = await fetch(url);
      if (r.ok) setInvoices(await r.json());
    } catch { /* silent */ }
    setLoading(false);
  }, [filterYear, filterMonth, filterClient, filterStatus]);

  useEffect(() => { if (token && isAdmin) load(token); }, [token, isAdmin, load]);

  async function handleUploadMultiple(files: FileList | File[]) {
    const pdfs = Array.from(files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
    const nonPdfs = Array.from(files).filter(f => !f.name.toLowerCase().endsWith('.pdf'));
    if (pdfs.length === 0) { setUploadMsg(''); setUploadError('PDF 파일이 없습니다.'); return; }

    setUploading(true); setUploadMsg(''); setUploadError(''); setUploadResults([]);
    const results: { name: string; ok: boolean; msg: string }[] = [];

    for (let i = 0; i < pdfs.length; i++) {
      const file = pdfs[i];
      setUploadProgress({ current: i + 1, total: pdfs.length, name: file.name });
      const fd = new FormData();
      fd.append('token', token);
      fd.append('file', file);
        try {
        const r = await fetch(`${API}/billing-invoice/upload`, { method: 'POST', body: fd });
        const d = await r.json();
        if (!r.ok) {
          const msg = r.status === 409 ? `⚠️ 중복: ${d.detail}` : (d.detail || '업로드 실패');
          throw new Error(msg);
        }
        results.push({ name: file.name, ok: true, msg: `${d.parsed?.client_name} / ${d.parsed?.service_month} — ${d.item_count}개 항목` });
      } catch (e) {
        results.push({ name: file.name, ok: false, msg: e instanceof Error ? e.message : '업로드 실패' });
      }
    }

    if (nonPdfs.length > 0) {
      results.push({ name: `${nonPdfs.length}개 파일`, ok: false, msg: 'PDF가 아닌 파일은 건너뜀' });
    }

    setUploadResults(results);
    setUploadProgress(null);
    setUploading(false);
    load(token);
  }

  async function handleDelete(id: string) {
    if (!confirm('삭제하시겠습니까?')) return;
    try {
      const r = await fetch(`${API}/billing-invoice/${id}?token=${token}`, { method: 'DELETE' });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        alert(`삭제 실패: ${d.detail || r.status}`);
        return;
      }
    } catch (e) {
      alert(`삭제 오류: ${e}`);
      return;
    }
    await load(token);
  }

  async function handleDeleteAll() {
    if (!confirm(`0원짜리 항목을 전체 삭제하시겠습니까?`)) return;
    try {
      const r = await fetch(`${API}/billing-invoice/cleanup-empty?token=${token}`, { method: 'DELETE' });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { alert(`삭제 실패: ${d.detail || r.status}`); return; }
      alert(`${d.deleted || 0}개 삭제됨`);
    } catch (e) { alert(`오류: ${e}`); }
    await load(token);
  }

  async function handleToggleStatus(inv: BillingInvoice) {
    const newStatus = inv.status === '완납' ? '미납' : '완납';
    const newPaid = newStatus === '완납' ? inv.total_amount : 0;
    try {
      const r = await fetch(`${API}/billing-invoice/${inv.id}?token=${token}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus, paid_amount: newPaid }),
      });
      if (!r.ok) { const d = await r.json().catch(() => ({})); alert(`변경 실패: ${d.detail || r.status}`); return; }
    } catch (e) { alert(`오류: ${e}`); return; }
    await load(token);
  }

  async function handleBulkComplete() {
    if (!confirm('현재 조회된 모든 인보이스를 완납으로 변경하시겠습니까?')) return;
    try {
      const r = await fetch(`${API}/billing-invoice/bulk-status?token=${token}&status=완납`, { method: 'PUT' });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { alert(`실패: ${d.detail || r.status}`); return; }
      alert(`✅ ${d.updated || 0}건 완납으로 변경됨`);
    } catch (e) { alert(`오류: ${e}`); }
    await load(token);
  }

  async function handleDedup() {
    try {
      const dr = await fetch(`${API}/billing-invoice/diagnostics?token=${token}`);
      const diag = await dr.json();
      const dupCount = diag.duplicate_groups?.length || 0;
      const totalDups = diag.duplicate_groups?.reduce((s: number, g: any) => s + (g.count - 1), 0) || 0;
      if (dupCount === 0) { alert(`중복 없음 — 전체 ${diag.total_invoices}건, 합계 ${(diag.total_amount || 0).toLocaleString()}원`); return; }
      const msg = `⚠️ 중복 발견: ${dupCount}그룹, ${totalDups}개 중복\n\n` +
        diag.duplicate_groups.slice(0, 5).map((g: any) => `• ${g.client_name} / ${g.service_month} / ${(g.total_amount || 0).toLocaleString()}원 × ${g.count}건`).join('\n') +
        (dupCount > 5 ? `\n... 외 ${dupCount - 5}그룹` : '') +
        `\n\n중복 제거하시겠습니까? (최신 1건만 보존)`;
      if (!confirm(msg)) return;
      const r2 = await fetch(`${API}/billing-invoice/dedup?token=${token}`, { method: 'DELETE' });
      const d2 = await r2.json().catch(() => ({}));
      if (!r2.ok) { alert(`실패: ${d2.detail || r2.status}`); return; }
      alert(`✅ ${d2.deleted || 0}개 중복 제거 완료`);
    } catch (e) { alert(`오류: ${e}`); }
    await load(token);
  }

  if (!isAdmin) return <div style={{ padding: '2rem', color: '#dc2626' }}>관리자 권한이 필요합니다.</div>;

  const totalBilled = invoices.reduce((s, r) => s + (r.total_amount || 0), 0);
  const totalUnpaid = invoices.reduce((s, r) => s + ((r.total_amount || 0) - (r.paid_amount || 0)), 0);

  // 서비스월별 집계 (로드된 데이터 기반)
  const monthlyMap: Record<string, { billed: number; paid: number }> = {};
  for (const inv of invoices) {
    const key = inv.service_month || inv.invoice_date?.slice(0, 7) || '미상';
    if (!monthlyMap[key]) monthlyMap[key] = { billed: 0, paid: 0 };
    monthlyMap[key].billed += inv.total_amount || 0;
    monthlyMap[key].paid += inv.paid_amount || 0;
  }
  const monthlySorted = Object.entries(monthlyMap).sort(([a], [b]) => a.localeCompare(b));
  const maxBilled = Math.max(...monthlySorted.map(([, v]) => v.billed), 1);

  return (
    <div style={{ padding: '1.25rem', maxWidth: 1100 }}>
      <div style={{ marginBottom: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <h2 style={{ fontSize: '1.375rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.2rem' }}>실 인보이스 관리</h2>
          <p style={{ color: '#6b7280', fontSize: '0.8rem' }}>PDF 청구서 업로드 → AI 자동 파싱 → 납부 추적</p>
        </div>
        {/* 탭 */}
        <div style={{ display: 'flex', gap: '0.35rem' }}>
          {([['list', '📋 목록'], ['analytics', '📊 분석']] as const).map(([tab, label]) => (
            <button key={tab} onClick={() => setActiveTab(tab)}
              style={{ padding: '0.4rem 1rem', borderRadius: 8, border: '1px solid', cursor: 'pointer', fontSize: '0.82rem', fontWeight: 600,
                borderColor: activeTab === tab ? '#1a3c6e' : '#e5e7eb',
                background: activeTab === tab ? '#1a3c6e' : 'white',
                color: activeTab === tab ? 'white' : '#374151' }}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {activeTab === 'list' && (<>
      {/* KPI */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem', marginBottom: '1.25rem' }}>        {[
          { label: '조회 건수', value: `${invoices.length}건`, color: '#1a3c6e' },
          { label: '총 청구액', value: totalBilled.toLocaleString() + '원', color: '#1d4ed8' },
          { label: '미수금', value: totalUnpaid.toLocaleString() + '원', color: totalUnpaid > 0 ? '#dc2626' : '#16a34a' },
        ].map(k => (
          <div key={k.label} style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '1rem', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
            <div style={{ fontSize: '0.72rem', color: '#9ca3af', marginBottom: '0.2rem' }}>{k.label}</div>
            <div style={{ fontSize: '1.3rem', fontWeight: 700, color: k.color }}>{k.value}</div>
          </div>
        ))}
      </div>

      {/* 월별 청구 현황 */}
      {monthlySorted.length > 0 && (
        <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '1rem', marginBottom: '1.25rem' }}>
          <div style={{ fontSize: '0.8rem', fontWeight: 700, color: '#374151', marginBottom: '0.75rem' }}>📊 서비스월별 청구 현황</div>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-end', overflowX: 'auto', paddingBottom: '0.25rem' }}>
            {monthlySorted.map(([month, v]) => {
              const barH = Math.max(Math.round((v.billed / maxBilled) * 80), 4);
              const paidH = Math.max(Math.round((v.paid / maxBilled) * 80), 0);
              const unpaid = v.billed - v.paid;
              return (
                <div key={month} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: 52, cursor: 'pointer' }}
                  onClick={() => {
                    const [y, m] = month.split('-');
                    if (y && m) { setFilterYear(Number(y)); setFilterMonth(Number(m)); }
                  }}
                  title={`${month}\n청구: ${v.billed.toLocaleString()}원\n납부: ${v.paid.toLocaleString()}원\n미수금: ${unpaid.toLocaleString()}원`}>
                  <div style={{ fontSize: '0.65rem', color: '#6b7280', marginBottom: '0.2rem', fontWeight: 600 }}>
                    {(v.billed / 10000).toFixed(0)}만
                  </div>
                  <div style={{ position: 'relative', width: 28, height: barH, borderRadius: '3px 3px 0 0', background: '#dbeafe', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', overflow: 'hidden' }}>
                    <div style={{ width: '100%', height: paidH, background: '#1d4ed8', borderRadius: '0 0 0 0' }} />
                    {unpaid > 0 && <div style={{ position: 'absolute', top: 0, right: 1, width: 4, height: 4, background: '#dc2626', borderRadius: '0 3px 0 0' }} />}
                  </div>
                  <div style={{ fontSize: '0.65rem', color: '#374151', marginTop: '0.25rem', whiteSpace: 'nowrap' }}>
                    {month.slice(2)}
                  </div>
                </div>
              );
            })}
          </div>
          <div style={{ display: 'flex', gap: '1rem', marginTop: '0.5rem', fontSize: '0.68rem', color: '#6b7280' }}>
            <span><span style={{ display: 'inline-block', width: 10, height: 10, background: '#1d4ed8', borderRadius: 2, marginRight: 3 }} />납부</span>
            <span><span style={{ display: 'inline-block', width: 10, height: 10, background: '#dbeafe', borderRadius: 2, marginRight: 3 }} />미수금</span>
            <span style={{ color: '#9ca3af' }}>※ 막대 클릭 시 해당 월 필터</span>
          </div>
        </div>
      )}

      {/* 업로드 존 */}
      <div
        onDragOver={e => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={e => { e.preventDefault(); setDrag(false); if (e.dataTransfer.files.length) handleUploadMultiple(e.dataTransfer.files); }}
        onClick={() => !uploading && fileRef.current?.click()}
        style={{
          border: `2px dashed ${drag ? '#1a3c6e' : '#d1d5db'}`,
          borderRadius: 10, padding: '1.5rem', textAlign: 'center',
          cursor: uploading ? 'default' : 'pointer', marginBottom: '1rem',
          background: drag ? '#eff6ff' : uploading ? '#f9fafb' : 'white',
          transition: 'all 0.2s',
        }}
      >
        <input ref={fileRef} type="file" accept=".pdf" multiple style={{ display: 'none' }}
          onChange={e => { if (e.target.files?.length) handleUploadMultiple(e.target.files); e.target.value = ''; }} />
        {uploading && uploadProgress
          ? <>
              <div style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>⏳</div>
              <p style={{ color: '#1a3c6e', fontWeight: 700, marginBottom: '0.3rem' }}>
                {uploadProgress.current} / {uploadProgress.total} 처리 중
              </p>
              <p style={{ color: '#6b7280', fontSize: '0.8rem', marginBottom: '0.5rem' }}>
                {uploadProgress.name}
              </p>
              <div style={{ background: '#e5e7eb', borderRadius: 99, height: 8, width: '80%', margin: '0 auto' }}>
                <div style={{
                  height: 8, borderRadius: 99, background: '#1a3c6e',
                  width: `${(uploadProgress.current / uploadProgress.total) * 100}%`,
                  transition: 'width 0.3s',
                }} />
              </div>
            </>
          : <>
              <div style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>📄</div>
              <p style={{ color: '#374151', fontWeight: 600 }}>PDF 청구서를 드래그하거나 클릭해서 업로드</p>
              <p style={{ color: '#9ca3af', fontSize: '0.78rem', marginTop: '0.25rem' }}>여러 파일 동시 업로드 가능 · 엑셀 기반 PDF만 지원 (스캔 불가)</p>
            </>
        }
      </div>

      {uploadMsg && <div style={{ padding: '0.75rem 1rem', background: '#f0fdf4', color: '#16a34a', borderRadius: 8, marginBottom: '0.75rem', fontSize: '0.875rem' }}>{uploadMsg}</div>}
      {uploadError && <div style={{ padding: '0.75rem 1rem', background: '#fef2f2', color: '#dc2626', borderRadius: 8, marginBottom: '0.75rem', fontSize: '0.875rem' }}>{uploadError}</div>}

      {uploadResults.length > 0 && (
        <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 8, marginBottom: '1rem', overflow: 'hidden' }}>
          <div style={{ padding: '0.6rem 1rem', background: '#f9fafb', borderBottom: '1px solid #e5e7eb', fontSize: '0.8rem', fontWeight: 600, color: '#374151', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>업로드 결과 — 성공 {uploadResults.filter(r => r.ok).length} / {uploadResults.filter(r => !r.msg.includes('건너뜀')).length}건</span>
            <button onClick={() => setUploadResults([])} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', fontSize: '1rem' }}>✕</button>
          </div>
          <div style={{ maxHeight: 220, overflowY: 'auto' }}>
            {uploadResults.map((r, i) => (
              <div key={i} style={{ padding: '0.4rem 1rem', borderBottom: '1px solid #f3f4f6', display: 'flex', gap: '0.5rem', alignItems: 'center', fontSize: '0.78rem' }}>
                <span>{r.ok ? '✅' : '❌'}</span>
                <span style={{ color: '#6b7280', flex: '0 0 auto', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={r.name}>{r.name}</span>
                <span style={{ color: r.ok ? '#16a34a' : '#dc2626', flex: 1 }}>{r.msg}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 필터 */}
      <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '0.75rem 1rem', marginBottom: '1rem' }}>
        {/* 연도 */}
        <div style={{ display: 'flex', gap: '0.4rem', marginBottom: '0.5rem', alignItems: 'center' }}>
          <span style={{ fontSize: '0.72rem', color: '#9ca3af', width: 28 }}>연도</span>
          {[2024, 2025, 2026, 2027].map(y => (
            <button key={y} onClick={() => { setFilterYear(y); setFilterMonth(0); }}
              style={{ padding: '0.25rem 0.65rem', border: '1px solid', borderColor: filterYear === y ? '#1a3c6e' : '#e5e7eb', background: filterYear === y ? '#1a3c6e' : 'white', color: filterYear === y ? 'white' : '#374151', borderRadius: 20, cursor: 'pointer', fontSize: '0.78rem', fontWeight: filterYear === y ? 700 : 400 }}>
              {y}
            </button>
          ))}
        </div>
        {/* 서비스월 */}
        <div style={{ display: 'flex', gap: '0.4rem', marginBottom: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.72rem', color: '#9ca3af', width: 28 }}>월</span>
          <button onClick={() => setFilterMonth(0)}
            style={{ padding: '0.25rem 0.65rem', border: '1px solid', borderColor: filterMonth === 0 ? '#6b7280' : '#e5e7eb', background: filterMonth === 0 ? '#6b7280' : 'white', color: filterMonth === 0 ? 'white' : '#374151', borderRadius: 20, cursor: 'pointer', fontSize: '0.78rem' }}>
            전체
          </button>
          {Array.from({ length: 12 }, (_, i) => i + 1).map(m => (
            <button key={m} onClick={() => setFilterMonth(m)}
              style={{ padding: '0.25rem 0.6rem', border: '1px solid', borderColor: filterMonth === m ? '#1d4ed8' : '#e5e7eb', background: filterMonth === m ? '#1d4ed8' : 'white', color: filterMonth === m ? 'white' : '#374151', borderRadius: 20, cursor: 'pointer', fontSize: '0.78rem', fontWeight: filterMonth === m ? 700 : 400 }}>
              {m}월
            </button>
          ))}
        </div>
        {/* 거래처 + 상태 + 빈항목 */}
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.72rem', color: '#9ca3af', width: 28 }}>검색</span>
          <input type="text" placeholder="거래처명" value={filterClient}
            onChange={e => setFilterClient(e.target.value)}
            style={{ padding: '0.28rem 0.6rem', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: '0.78rem', width: 110 }} />
          <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
            style={{ padding: '0.28rem 0.6rem', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: '0.78rem' }}>
            <option value="">전체 상태</option>
            {['미납', '부분납', '완납'].map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <button onClick={() => setFilterStatus(filterStatus === '미납' ? '' : '미납')}
            style={{ padding: '0.28rem 0.65rem', background: filterStatus === '미납' ? '#fef2f2' : 'white', color: '#dc2626', border: `1px solid ${filterStatus === '미납' ? '#dc2626' : '#e5e7eb'}`, borderRadius: 6, cursor: 'pointer', fontSize: '0.72rem', fontWeight: filterStatus === '미납' ? 700 : 400 }}>
            미납만
          </button>
          <button onClick={handleDeleteAll}
            style={{ marginLeft: 'auto', padding: '0.28rem 0.65rem', background: '#fef2f2', color: '#dc2626', border: '1px solid #fecaca', borderRadius: 6, cursor: 'pointer', fontSize: '0.72rem', fontWeight: 600 }}>
            🗑 빈 항목 정리
          </button>
          <button onClick={handleDedup}
            style={{ padding: '0.28rem 0.65rem', background: '#fff7ed', color: '#ea580c', border: '1px solid #fed7aa', borderRadius: 6, cursor: 'pointer', fontSize: '0.72rem', fontWeight: 600 }}>
            🔍 중복 진단/제거
          </button>
          <button onClick={handleBulkComplete}
            style={{ padding: '0.28rem 0.65rem', background: '#f0fdf4', color: '#16a34a', border: '1px solid #bbf7d0', borderRadius: 6, cursor: 'pointer', fontSize: '0.72rem', fontWeight: 600 }}>
            ✅ 전체 완납 설정
          </button>
        </div>
      </div>

      {/* 목록 테이블 */}
      <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, overflow: 'hidden' }}>
        {loading ? (
          <p style={{ padding: '2rem', textAlign: 'center', color: '#9ca3af' }}>로딩 중...</p>
        ) : invoices.length === 0 ? (
          <p style={{ padding: '2rem', textAlign: 'center', color: '#9ca3af' }}>등록된 청구서가 없습니다.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
              <thead>
                <tr style={{ background: '#1a3c6e', color: 'white' }}>
                  {['청구일', '거래처', '서비스월', '청구합계', '입금액', '미수금', '상태', '업로더', ''].map(h => (
                    <th key={h} style={{ padding: '0.6rem 0.75rem', textAlign: 'left', whiteSpace: 'nowrap', fontWeight: 600 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {invoices.map((inv, i) => {
                  const unpaid = (inv.total_amount || 0) - (inv.paid_amount || 0);
                  const overdue = inv.due_date && inv.due_date < new Date().toISOString().slice(0, 10) && inv.status !== '완납';
                  return (
                    <tr key={inv.id} style={{ borderBottom: '1px solid #f3f4f6', background: overdue ? '#fff5f5' : i % 2 === 0 ? 'white' : '#fafafa' }}>
                      <td style={{ padding: '0.55rem 0.75rem', whiteSpace: 'nowrap' }}>{fmtDt(inv.invoice_date)}{overdue && <span style={{ marginLeft: 4, color: '#dc2626', fontSize: '0.68rem' }}>연체</span>}</td>
                      <td style={{ padding: '0.55rem 0.75rem', fontWeight: 600 }}>{inv.client_name}</td>
                      <td style={{ padding: '0.55rem 0.75rem', color: '#6b7280' }}>{inv.service_month || '-'}</td>
                      <td style={{ padding: '0.55rem 0.75rem', fontWeight: 600 }}>{(inv.total_amount || 0).toLocaleString()}</td>
                      <td style={{ padding: '0.55rem 0.75rem', color: '#16a34a' }}>{(inv.paid_amount || 0).toLocaleString()}</td>
                      <td style={{ padding: '0.55rem 0.75rem', color: unpaid > 0 ? '#dc2626' : '#16a34a', fontWeight: unpaid > 0 ? 700 : 400 }}>{unpaid.toLocaleString()}</td>
                      <td style={{ padding: '0.55rem 0.75rem' }}>
                        <button
                          onClick={(e) => { e.stopPropagation(); handleToggleStatus(inv); }}
                          title={inv.status === '완납' ? '클릭하면 미납으로 변경' : '클릭하면 완납으로 변경'}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                          <StatusBadge status={inv.status} />
                        </button>
                      </td>
                      <td style={{ padding: '0.55rem 0.75rem', color: '#9ca3af' }}>{inv.created_by || '-'}</td>
                      <td style={{ padding: '0.4rem 0.75rem' }}>
                        <div style={{ display: 'flex', gap: '0.35rem' }}>
                          <button onClick={(e) => { e.stopPropagation(); setDetailId(inv.id); }} style={{ ...btnSm, background: '#eff6ff', color: '#1d4ed8' }}>상세</button>
                          <button onClick={(e) => { e.stopPropagation(); setPayingInv(inv); }} style={{ ...btnSm, background: '#f0fdf4', color: '#16a34a' }}>납부</button>
                          <button onClick={(e) => { e.stopPropagation(); handleDelete(inv.id); }} style={{ ...btnSm, background: '#fef2f2', color: '#dc2626' }}>삭제</button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      </>)}

      {/* ── 분석 탭 ─────────────────────────────────────────────── */}
      {activeTab === 'analytics' && (
        <div>
          {/* 연도 선택 */}
          <div style={{ display: 'flex', gap: '0.4rem', marginBottom: '1rem', alignItems: 'center' }}>
            <span style={{ fontSize: '0.78rem', color: '#6b7280' }}>분석 연도:</span>
            {[2024, 2025, 2026, 2027].map(y => (
              <button key={y} onClick={() => setAnalyticsYear(y)}
                style={{ padding: '0.3rem 0.7rem', borderRadius: 20, border: '1px solid', cursor: 'pointer', fontSize: '0.78rem', fontWeight: analyticsYear === y ? 700 : 400,
                  borderColor: analyticsYear === y ? '#1a3c6e' : '#e5e7eb',
                  background: analyticsYear === y ? '#1a3c6e' : 'white',
                  color: analyticsYear === y ? 'white' : '#374151' }}>
                {y}
              </button>
            ))}
          </div>

          {analyticsLoading ? (
            <div style={{ padding: '3rem', textAlign: 'center', color: '#9ca3af' }}>분석 데이터 로딩 중...</div>
          ) : !analytics ? (
            <div style={{ padding: '3rem', textAlign: 'center', color: '#9ca3af' }}>데이터 없음</div>
          ) : (
            <>
              {/* KPI 요약 */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '0.6rem', marginBottom: '1.25rem' }}>
                {[
                  { label: '청구 건수', value: `${analytics.summary.invoice_count}건`, color: '#1a3c6e', sub: null },
                  { label: '총 청구액', value: `${(analytics.summary.total_billed / 10000).toFixed(0)}만원`, color: '#1d4ed8', sub: null },
                  { label: '총 납부액', value: `${(analytics.summary.total_paid / 10000).toFixed(0)}만원`, color: '#16a34a', sub: null },
                  { label: '미수금', value: `${(analytics.summary.total_unpaid / 10000).toFixed(0)}만원`, color: analytics.summary.total_unpaid > 0 ? '#dc2626' : '#16a34a', sub: null },
                  { label: '납부율', value: `${analytics.summary.payment_rate}%`, color: analytics.summary.payment_rate >= 80 ? '#16a34a' : '#ea580c', sub: `완납 ${analytics.summary.status_breakdown['완납']}건` },
                ].map(k => (
                  <div key={k.label} style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '0.85rem', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
                    <div style={{ fontSize: '0.68rem', color: '#9ca3af', marginBottom: '0.15rem' }}>{k.label}</div>
                    <div style={{ fontSize: '1.15rem', fontWeight: 700, color: k.color }}>{k.value}</div>
                    {k.sub && <div style={{ fontSize: '0.65rem', color: '#6b7280', marginTop: '0.1rem' }}>{k.sub}</div>}
                  </div>
                ))}
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                {/* 월별 청구 추이 */}
                <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '1rem' }}>
                  <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#374151', marginBottom: '0.75rem' }}>📅 서비스월별 청구 추이</div>
                  {analytics.monthly.length === 0 ? <div style={{ color: '#9ca3af', fontSize: '0.8rem' }}>데이터 없음</div> : (
                    <div>
                      {analytics.monthly.map((m: any) => {
                        const maxT = Math.max(...analytics.monthly.map((x: any) => x.total), 1);
                        const barW = Math.max(Math.round(m.total / maxT * 100), 2);
                        const paidW = Math.max(Math.round(m.paid / maxT * 100), 0);
                        return (
                          <div key={m.month} style={{ marginBottom: '0.55rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: '#374151', marginBottom: '0.2rem' }}>
                              <span style={{ fontWeight: 600 }}>{m.month}</span>
                              <span style={{ color: '#6b7280' }}>
                                {(m.total / 10000).toFixed(0)}만원
                                {m.mom_change != null && (
                                  <span style={{ marginLeft: 6, color: m.mom_change > 0 ? '#dc2626' : '#16a34a', fontSize: '0.68rem' }}>
                                    {m.mom_change > 0 ? '▲' : '▼'}{Math.abs(m.mom_change)}%
                                  </span>
                                )}
                                <span style={{ marginLeft: 6, color: m.payment_rate >= 100 ? '#16a34a' : '#ea580c' }}>납부율 {m.payment_rate}%</span>
                              </span>
                            </div>
                            <div style={{ position: 'relative', height: 12, background: '#f3f4f6', borderRadius: 6 }}>
                              <div style={{ position: 'absolute', left: 0, top: 0, height: '100%', width: `${barW}%`, background: '#dbeafe', borderRadius: 6 }} />
                              <div style={{ position: 'absolute', left: 0, top: 0, height: '100%', width: `${paidW}%`, background: '#1d4ed8', borderRadius: 6 }} />
                            </div>
                          </div>
                        );
                      })}
                      <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem', fontSize: '0.65rem', color: '#6b7280' }}>
                        <span><span style={{ display: 'inline-block', width: 8, height: 8, background: '#1d4ed8', borderRadius: 2, marginRight: 3 }} />납부</span>
                        <span><span style={{ display: 'inline-block', width: 8, height: 8, background: '#dbeafe', borderRadius: 2, marginRight: 3 }} />미수금</span>
                      </div>
                    </div>
                  )}
                </div>

                {/* 카테고리별 비중 */}
                <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '1rem' }}>
                  <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#374151', marginBottom: '0.75rem' }}>📦 비용 카테고리 분석</div>
                  {analytics.by_category.length === 0 ? <div style={{ color: '#9ca3af', fontSize: '0.8rem' }}>데이터 없음</div> : (
                    <div>
                      {analytics.by_category.map((c: any) => (
                        <div key={c.category} style={{ marginBottom: '0.55rem' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', marginBottom: '0.2rem' }}>
                            <span style={{ fontWeight: 600, color: '#374151' }}>{c.category}</span>
                            <span style={{ color: '#6b7280' }}>{(c.total / 10000).toFixed(0)}만원 <span style={{ color: '#1d4ed8' }}>({c.ratio}%)</span></span>
                          </div>
                          <div style={{ height: 10, background: '#f3f4f6', borderRadius: 5 }}>
                            <div style={{ height: '100%', width: `${c.ratio}%`, background: catColor(c.category), borderRadius: 5 }} />
                          </div>
                        </div>
                      ))}
                      {analytics.deductions.length > 0 && (
                        <div style={{ marginTop: '0.5rem', paddingTop: '0.5rem', borderTop: '1px solid #f3f4f6' }}>
                          <div style={{ fontSize: '0.68rem', color: '#6b7280', marginBottom: '0.3rem' }}>차감 항목</div>
                          {analytics.deductions.map((d: any) => (
                            <div key={d.category} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: '#dc2626' }}>
                              <span>{d.category}</span><span>{d.total.toLocaleString()}원</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                {/* 거래처별 현황 */}
                <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '1rem' }}>
                  <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#374151', marginBottom: '0.75rem' }}>🏢 거래처별 청구 현황</div>
                  {analytics.by_client.length === 0 ? <div style={{ color: '#9ca3af', fontSize: '0.8rem' }}>데이터 없음</div> : (
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.75rem' }}>
                      <thead>
                        <tr style={{ borderBottom: '1px solid #e5e7eb', color: '#6b7280' }}>
                          <th style={{ padding: '0.3rem 0.4rem', textAlign: 'left', fontWeight: 600 }}>거래처</th>
                          <th style={{ padding: '0.3rem 0.4rem', textAlign: 'right', fontWeight: 600 }}>청구액</th>
                          <th style={{ padding: '0.3rem 0.4rem', textAlign: 'right', fontWeight: 600 }}>미수금</th>
                          <th style={{ padding: '0.3rem 0.4rem', textAlign: 'center', fontWeight: 600 }}>납부율</th>
                        </tr>
                      </thead>
                      <tbody>
                        {analytics.by_client.map((c: any) => (
                          <tr key={c.client_name} style={{ borderBottom: '1px solid #f9fafb' }}>
                            <td style={{ padding: '0.35rem 0.4rem', fontWeight: 600, color: '#1a3c6e' }}>{c.client_name}</td>
                            <td style={{ padding: '0.35rem 0.4rem', textAlign: 'right', color: '#374151' }}>{(c.total / 10000).toFixed(0)}만</td>
                            <td style={{ padding: '0.35rem 0.4rem', textAlign: 'right', color: c.unpaid > 0 ? '#dc2626' : '#16a34a', fontWeight: c.unpaid > 0 ? 700 : 400 }}>
                              {c.unpaid > 0 ? `${(c.unpaid / 10000).toFixed(0)}만` : '완납'}
                            </td>
                            <td style={{ padding: '0.35rem 0.4rem' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                <div style={{ flex: 1, height: 6, background: '#f3f4f6', borderRadius: 3 }}>
                                  <div style={{ height: '100%', width: `${Math.min(c.payment_rate, 100)}%`, background: c.payment_rate >= 100 ? '#16a34a' : c.payment_rate >= 50 ? '#f59e0b' : '#dc2626', borderRadius: 3 }} />
                                </div>
                                <span style={{ fontSize: '0.68rem', color: '#6b7280', minWidth: 28, textAlign: 'right' }}>{c.payment_rate}%</span>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>

                {/* 납부 패턴 & 미수금 */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {/* 납부 소요일 */}
                  {analytics.payment_speed.length > 0 && (
                    <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '1rem' }}>
                      <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#374151', marginBottom: '0.6rem' }}>💳 평균 납부 소요일 (완납 기준)</div>
                      {analytics.payment_speed.map((p: any) => (
                        <div key={p.client_name} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', padding: '0.25rem 0', borderBottom: '1px solid #f9fafb' }}>
                          <span style={{ color: '#374151', fontWeight: 500 }}>{p.client_name}</span>
                          <span style={{ color: p.avg_days > 30 ? '#dc2626' : p.avg_days > 14 ? '#ea580c' : '#16a34a', fontWeight: 700 }}>
                            {p.avg_days != null ? `${p.avg_days}일` : '-'} <span style={{ color: '#9ca3af', fontWeight: 400 }}>({p.count}건)</span>
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* 연체/미수금 */}
                  {analytics.unpaid_list.length > 0 && (
                    <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '1rem' }}>
                      <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#374151', marginBottom: '0.6rem' }}>
                        ⚠️ 미수금 현황 <span style={{ fontSize: '0.7rem', color: '#dc2626', marginLeft: 4 }}>
                          {analytics.unpaid_list.filter((u: any) => u.overdue).length}건 연체
                        </span>
                      </div>
                      <div style={{ maxHeight: 200, overflowY: 'auto' }}>
                        {analytics.unpaid_list.map((u: any) => (
                          <div key={u.id} style={{ padding: '0.35rem 0', borderBottom: '1px solid #f9fafb', fontSize: '0.73rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                              <span style={{ fontWeight: 600, color: u.overdue ? '#dc2626' : '#374151' }}>
                                {u.overdue && '🔴 '}{u.client_name}
                              </span>
                              <span style={{ color: '#dc2626', fontWeight: 700 }}>
                                {(u.unpaid_amount / 10000).toFixed(1)}만원
                              </span>
                            </div>
                            <div style={{ color: '#6b7280', fontSize: '0.68rem', marginTop: 1 }}>
                              {u.service_month || u.invoice_date} · {u.status}
                              {u.overdue_days && <span style={{ color: '#dc2626', marginLeft: 6 }}>연체 {u.overdue_days}일</span>}
                              {u.due_date && !u.overdue && <span style={{ marginLeft: 6 }}>납기 {u.due_date}</span>}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* 업체별 카테고리 비용 비율 */}
              {analytics.by_client_category?.length > 0 && (
                <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '1rem', marginBottom: '1rem' }}>
                  <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#374151', marginBottom: '0.75rem' }}>🏢 업체별 비용 카테고리 비율</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '0.75rem' }}>
                    {analytics.by_client_category.map((c: any) => (
                      <div key={c.client_name} style={{ border: '1px solid #f3f4f6', borderRadius: 8, padding: '0.65rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                          <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#1a3c6e' }}>{c.client_name}</span>
                          <span style={{ fontSize: '0.7rem', color: '#6b7280' }}>총 {(c.total / 10000).toFixed(0)}만원</span>
                        </div>
                        {c.categories.map((cat: any) => (
                          <div key={cat.category} style={{ marginBottom: '0.3rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.68rem', marginBottom: '0.15rem' }}>
                              <span style={{ color: catColor(cat.category), fontWeight: 600 }}>{cat.category}</span>
                              <span style={{ color: '#6b7280' }}>{(cat.total / 10000).toFixed(1)}만 ({cat.ratio}%)</span>
                            </div>
                            <div style={{ height: 7, background: '#f3f4f6', borderRadius: 4 }}>
                              <div style={{ height: '100%', width: `${cat.ratio}%`, background: catColor(cat.category), borderRadius: 4, opacity: 0.8 }} />
                            </div>
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 월별 카테고리 추이 */}
              {analytics.monthly_category?.length > 0 && (
                <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '1rem', marginBottom: '1rem' }}>
                  <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#374151', marginBottom: '0.75rem' }}>📈 월별 카테고리 비용 추이</div>
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ borderCollapse: 'collapse', fontSize: '0.72rem', minWidth: '100%' }}>
                      <thead>
                        <tr style={{ background: '#f9fafb' }}>
                          <th style={{ padding: '0.4rem 0.6rem', textAlign: 'left', color: '#6b7280', fontWeight: 600, whiteSpace: 'nowrap', borderBottom: '1px solid #e5e7eb' }}>카테고리</th>
                          {analytics.monthly_category.map((m: any) => (
                            <th key={m.month} style={{ padding: '0.4rem 0.6rem', textAlign: 'right', color: '#1a3c6e', fontWeight: 700, whiteSpace: 'nowrap', borderBottom: '1px solid #e5e7eb' }}>{m.month.slice(2)}</th>
                          ))}
                          <th style={{ padding: '0.4rem 0.6rem', textAlign: 'right', color: '#374151', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>합계</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(() => {
                          const allCats = Array.from(new Set(analytics.monthly_category.flatMap((m: any) => Object.keys(m.categories)))).sort((a: any, b: any) => {
                            const totA = analytics.monthly_category.reduce((s: number, m: any) => s + (m.categories[a] || 0), 0);
                            const totB = analytics.monthly_category.reduce((s: number, m: any) => s + (m.categories[b] || 0), 0);
                            return totB - totA;
                          });
                          return allCats.map((cat: any) => {
                            const rowTotal = analytics.monthly_category.reduce((s: number, m: any) => s + (m.categories[cat] || 0), 0);
                            const maxVal = Math.max(...analytics.monthly_category.map((m: any) => m.categories[cat] || 0), 1);
                            return (
                              <tr key={cat} style={{ borderBottom: '1px solid #f9fafb' }}>
                                <td style={{ padding: '0.35rem 0.6rem', whiteSpace: 'nowrap' }}>
                                  <span style={{ display: 'inline-block', width: 8, height: 8, background: catColor(cat), borderRadius: 2, marginRight: 5 }} />
                                  <span style={{ fontWeight: 600, color: '#374151' }}>{cat}</span>
                                </td>
                                {analytics.monthly_category.map((m: any) => {
                                  const val = m.categories[cat] || 0;
                                  const intensity = Math.round((val / maxVal) * 100);
                                  return (
                                    <td key={m.month} style={{ padding: '0.35rem 0.6rem', textAlign: 'right',
                                      background: val > 0 ? `${catColor(cat)}${Math.round(intensity * 0.3 + 10).toString(16).padStart(2, '0')}` : 'transparent',
                                      color: val > 0 ? '#111' : '#d1d5db', fontWeight: val > 0 ? 600 : 400 }}>
                                      {val > 0 ? `${(val / 10000).toFixed(0)}만` : '-'}
                                    </td>
                                  );
                                })}
                                <td style={{ padding: '0.35rem 0.6rem', textAlign: 'right', fontWeight: 700, color: '#1a3c6e' }}>
                                  {(rowTotal / 10000).toFixed(0)}만
                                </td>
                              </tr>
                            );
                          });
                        })()}
                        {/* 월 합계 행 */}
                        <tr style={{ background: '#f9fafb', borderTop: '2px solid #e5e7eb' }}>
                          <td style={{ padding: '0.35rem 0.6rem', fontWeight: 700, color: '#374151' }}>월 합계</td>
                          {analytics.monthly_category.map((m: any) => (
                            <td key={m.month} style={{ padding: '0.35rem 0.6rem', textAlign: 'right', fontWeight: 700, color: '#1a3c6e' }}>
                              {(m.total / 10000).toFixed(0)}만
                            </td>
                          ))}
                          <td style={{ padding: '0.35rem 0.6rem', textAlign: 'right', fontWeight: 700, color: '#dc2626' }}>
                            {(analytics.monthly_category.reduce((s: number, m: any) => s + m.total, 0) / 10000).toFixed(0)}만
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

            </>
          )}
        </div>
      )}

      {payingInv && <PayModal inv={payingInv} token={token} onClose={() => setPayingInv(null)} onSaved={() => load(token)} />}
      {detailId && <DetailModal invId={detailId} token={token} onClose={() => setDetailId(null)} />}
    </div>
  );
}

function catColor(cat: string): string {
  const map: Record<string, string> = {
    '택배비': '#3b82f6', '포장비': '#8b5cf6', '입출고비': '#f59e0b',
    '보관료': '#10b981', '바코드': '#6366f1', '도서산간': '#ec4899',
    '부대비용': '#14b8a6', '차감': '#ef4444', '기타': '#9ca3af',
  };
  return map[cat] || '#9ca3af';
}

const btnBlue: React.CSSProperties = { padding: '0.45rem 1rem', background: '#1a3c6e', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: '0.875rem' };
const btnGray: React.CSSProperties = { padding: '0.45rem 1rem', background: '#6b7280', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: '0.875rem' };
const btnSm: React.CSSProperties = { padding: '0.25rem 0.6rem', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: '0.72rem', fontWeight: 600, whiteSpace: 'nowrap' };
