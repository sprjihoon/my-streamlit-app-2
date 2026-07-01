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
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const tok = localStorage.getItem('token') || '';
    const admin = localStorage.getItem('isAdmin') === 'true';
    setToken(tok);
    setIsAdmin(admin);
    if (!admin) { setLoading(false); return; }
    load(tok);
  }, []); // eslint-disable-line

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
        if (!r.ok) throw new Error(d.detail || '업로드 실패');
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
    await fetch(`${API}/billing-invoice/${id}?token=${token}`, { method: 'DELETE' });
    load(token);
  }

  if (!isAdmin) return <div style={{ padding: '2rem', color: '#dc2626' }}>관리자 권한이 필요합니다.</div>;

  const totalBilled = invoices.reduce((s, r) => s + (r.total_amount || 0), 0);
  const totalUnpaid = invoices.reduce((s, r) => s + ((r.total_amount || 0) - (r.paid_amount || 0)), 0);

  return (
    <div style={{ padding: '1.25rem', maxWidth: 1100 }}>
      <div style={{ marginBottom: '1.25rem' }}>
        <h2 style={{ fontSize: '1.375rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.2rem' }}>실 인보이스 관리</h2>
        <p style={{ color: '#6b7280', fontSize: '0.8rem' }}>PDF 청구서 업로드 → AI 자동 파싱 → 납부 추적</p>
      </div>

      {/* KPI */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem', marginBottom: '1.25rem' }}>
        {[
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
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
        {[2024, 2025, 2026, 2027].map(y => (
          <button key={y} onClick={() => setFilterYear(y)}
            style={{ padding: '0.35rem 0.75rem', border: '1px solid', borderColor: filterYear === y ? '#1a3c6e' : '#d1d5db', background: filterYear === y ? '#1a3c6e' : 'white', color: filterYear === y ? 'white' : '#374151', borderRadius: 6, cursor: 'pointer', fontSize: '0.8rem' }}>
            {y}년
          </button>
        ))}
        <select value={filterMonth} onChange={e => setFilterMonth(Number(e.target.value))}
          style={{ padding: '0.35rem 0.6rem', border: '1px solid #d1d5db', borderRadius: 6, fontSize: '0.8rem' }}>
          <option value={0}>전체 월</option>
          {Array.from({ length: 12 }, (_, i) => i + 1).map(m => <option key={m} value={m}>{m}월</option>)}
        </select>
        <input type="text" placeholder="거래처 검색" value={filterClient}
          onChange={e => setFilterClient(e.target.value)}
          style={{ padding: '0.35rem 0.6rem', border: '1px solid #d1d5db', borderRadius: 6, fontSize: '0.8rem', width: 120 }} />
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
          style={{ padding: '0.35rem 0.6rem', border: '1px solid #d1d5db', borderRadius: 6, fontSize: '0.8rem' }}>
          <option value="">전체 상태</option>
          {['미납', '부분납', '완납'].map(s => <option key={s} value={s}>{s}</option>)}
        </select>
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
                      <td style={{ padding: '0.55rem 0.75rem' }}><StatusBadge status={inv.status} /></td>
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

      {payingInv && <PayModal inv={payingInv} token={token} onClose={() => setPayingInv(null)} onSaved={() => load(token)} />}
      {detailId && <DetailModal invId={detailId} token={token} onClose={() => setDetailId(null)} />}
    </div>
  );
}

const btnBlue: React.CSSProperties = { padding: '0.45rem 1rem', background: '#1a3c6e', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: '0.875rem' };
const btnGray: React.CSSProperties = { padding: '0.45rem 1rem', background: '#6b7280', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: '0.875rem' };
const btnSm: React.CSSProperties = { padding: '0.25rem 0.6rem', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: '0.72rem', fontWeight: 600, whiteSpace: 'nowrap' };
