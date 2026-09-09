'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import { Alert } from '@/components/Alert';
import {
  listInboundBatches,
  createInboundBatch,
  getInboundBatch,
  updateInboundBatch,
  runInboundOcr,
  updateInboundItem,
  addInboundItem,
  deleteInboundItem,
  closeInboundBatch,
  deleteInboundBatch,
  listInboundVendors,
  downloadInboundBarcodePdf,
  upsertVendorAlias,
  getRepairBarcodes,
  getVendorAliases,
  getInboundFilterOptions,
  InboundAliasGroup,
  InboundBatch,
  InboundItem,
  InboundRegisteredVendor,
  VendorAlias,
  RepairBarcode,
} from '@/lib/api';

// ─────────────────────────────────────
// 스타일 상수
// ─────────────────────────────────────

const btn = (bg: string, hover?: string): React.CSSProperties => ({
  padding: '0.45rem 1rem',
  backgroundColor: bg,
  color: '#fff',
  border: 'none',
  borderRadius: 'var(--radius-sm)',
  cursor: 'pointer',
  fontWeight: 500,
  fontSize: '0.85rem',
});

const btnOutline: React.CSSProperties = {
  padding: '0.45rem 1rem',
  backgroundColor: '#fff',
  color: 'var(--text-secondary)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)',
  cursor: 'pointer',
  fontSize: '0.85rem',
};

const inputStyle: React.CSSProperties = {
  padding: '0.45rem 0.65rem',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)',
  fontSize: '0.85rem',
  outline: 'none',
  background: '#fff',
};

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: '0.8rem',
  fontWeight: 600,
  marginBottom: '0.3rem',
  color: 'var(--text-secondary)',
};

// ─────────────────────────────────────
// 상태 배지
// ─────────────────────────────────────

const STATUS_COLOR: Record<string, { bg: string; color: string }> = {
  ocr_pending:  { bg: '#f3f4f6', color: '#6b7280' },
  confirming:   { bg: '#fef9c3', color: '#a16207' },
  inbound_done: { bg: '#dbeafe', color: '#1d4ed8' },
  grading:      { bg: '#ede9fe', color: '#7c3aed' },
  repairing:    { bg: '#ffedd5', color: '#c2410c' },
  done:         { bg: '#dcfce7', color: '#15803d' },
  cancelled:    { bg: '#fee2e2', color: '#dc2626' },
};

const ITEM_STATUS_COLOR: Record<string, { bg: string; color: string }> = {
  pending:       { bg: '#f3f4f6', color: '#6b7280' },
  confirmed:     { bg: '#dcfce7', color: '#15803d' },
  missing:       { bg: '#fee2e2', color: '#dc2626' },
  defect:        { bg: '#ffedd5', color: '#c2410c' },
  repair:        { bg: '#fef9c3', color: '#a16207' },
  unrecoverable: { bg: '#fecaca', color: '#991b1b' },
  done:          { bg: '#bbf7d0', color: '#166534' },
  etc:           { bg: '#ede9fe', color: '#7c3aed' },
};

const ITEM_STATUS_LABELS: Record<string, string> = {
  pending: '확인 전',
  confirmed: '정상',
  missing: '미입고',
  defect: '불량',
  repair: '수선대기',
  unrecoverable: '회생불가',
  done: '완료',
  etc: '기타',
};

function StatusBadge({ status, label, map }: { status: string; label: string; map: Record<string, { bg: string; color: string }> }) {
  const c = map[status] || { bg: '#f3f4f6', color: '#6b7280' };
  return (
    <span style={{
      padding: '2px 10px', borderRadius: 12,
      fontSize: '0.75rem', fontWeight: 600,
      backgroundColor: c.bg, color: c.color,
      whiteSpace: 'nowrap',
    }}>
      {label}
    </span>
  );
}

// ─────────────────────────────────────
// 유틸
// ─────────────────────────────────────

function getToken() {
  if (typeof window === 'undefined') return '';
  return localStorage.getItem('token') || '';
}

function fmt(dt: string | null) {
  if (!dt) return '-';
  return dt.replace('T', ' ').slice(0, 16);
}

function todayStr() {
  return new Date().toISOString().split('T')[0];
}

// ─────────────────────────────────────
// 오버레이 모달
// ─────────────────────────────────────

function Modal({ title, onClose, children, wide }: {
  title: string; onClose: () => void; children: React.ReactNode; wide?: boolean;
}) {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.45)',
      display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
      paddingTop: '3rem', paddingBottom: '2rem',
      overflowY: 'auto',
    }}>
      <div style={{
        background: '#fff',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-lg)',
        width: '100%',
        maxWidth: wide ? '900px' : '520px',
        margin: '0 1rem 2rem',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '1.1rem 1.5rem',
          borderBottom: '1px solid var(--border)',
        }}>
          <h2 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)' }}>{title}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: '1.4rem', cursor: 'pointer', color: 'var(--text-secondary)', lineHeight: 1 }}>×</button>
        </div>
        <div style={{ padding: '1.5rem' }}>{children}</div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────
// 품목 행 컴포넌트
// ─────────────────────────────────────

function ItemRow({ item, token, onUpdated, onDelete, batchVendor, batchDate, batchWholesale, batchCreatedBy }: {
  item: InboundItem;
  token: string;
  onUpdated: () => void;
  onDelete?: () => void;
  batchVendor?: string;
  batchDate?: string;
  batchWholesale?: string | null;
  batchCreatedBy?: string | null;
}) {
  const [actualQty, setActualQty] = useState(item.actual_qty);
  const [missingQty, setMissingQty] = useState(item.missing_qty);
  const [status, setStatus] = useState(item.status);
  const [saving, setSaving] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [editForm, setEditForm] = useState({
    matched_barcode: item.matched_barcode || '',
    matched_vendor: item.matched_vendor || '',
    matched_product: item.matched_product || '',
    matched_option: item.matched_option || '',
    supplier_location: item.supplier_location || '',
    supplier_contact: item.supplier_contact || '',
    memo: item.memo || '',
  });
  const [editSaving, setEditSaving] = useState(false);

  // ── 수정폼 바코드 검색 ──
  const [editBarcodeQ,       setEditBarcodeQ]       = useState('');
  const [editBarcodeResults, setEditBarcodeResults] = useState<RepairBarcode[]>([]);
  const [editBarcodeLoading, setEditBarcodeLoading] = useState(false);
  const [editBarcodeOpen,    setEditBarcodeOpen]    = useState(false);
  const [editBarcodeSelected, setEditBarcodeSelected] = useState<RepairBarcode | null>(null);
  const editBarcodeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const editBarcodeRef   = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function h(e: MouseEvent) {
      if (editBarcodeRef.current && !editBarcodeRef.current.contains(e.target as Node))
        setEditBarcodeOpen(false);
    }
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  function handleEditBarcodeInput(val: string) {
    setEditBarcodeQ(val); setEditBarcodeSelected(null); setEditBarcodeOpen(true);
    if (editBarcodeTimer.current) clearTimeout(editBarcodeTimer.current);
    if (!val.trim()) { setEditBarcodeResults([]); return; }
    editBarcodeTimer.current = setTimeout(async () => {
      setEditBarcodeLoading(true);
      try {
        const r = await getRepairBarcodes({ q: val.trim(), limit: 40 });
        setEditBarcodeResults(r.items);
      } catch { setEditBarcodeResults([]); }
      finally { setEditBarcodeLoading(false); }
    }, 350);
  }

  function selectEditBarcode(b: RepairBarcode) {
    setEditBarcodeSelected(b);
    setEditBarcodeQ(`${b.바코드} — ${b.제품명}${b.옵션 ? ' / ' + b.옵션 : ''}`);
    setEditBarcodeOpen(false);
    setEditForm(f => ({
      ...f,
      matched_barcode:  b.바코드,
      matched_vendor:   b.업체명 || f.matched_vendor,
      matched_product:  b.제품명 || f.matched_product,
      matched_option:   b.옵션  || f.matched_option,
    }));
  }

  async function save() {
    setSaving(true);
    try {
      await updateInboundItem(token, item.id, { actual_qty: actualQty, missing_qty: missingQty, status });
      onUpdated();
    } catch {
      alert('저장 실패');
    } finally {
      setSaving(false);
    }
  }

  async function saveEdit() {
    setEditSaving(true);
    try {
      await updateInboundItem(token, item.id, {
        matched_barcode: editForm.matched_barcode || undefined,
        matched_vendor: editForm.matched_vendor || undefined,
        matched_product: editForm.matched_product || undefined,
        matched_option: editForm.matched_option || undefined,
        supplier_location: editForm.supplier_location || undefined,
        supplier_contact: editForm.supplier_contact || undefined,
        memo: editForm.memo || undefined,
      });
      setEditMode(false);
      onUpdated();
    } catch {
      alert('수정 저장 실패');
    } finally {
      setEditSaving(false);
    }
  }

  const tdStyle: React.CSSProperties = { padding: '0.5rem 0.6rem', fontSize: '0.8rem', verticalAlign: 'middle', borderBottom: '1px solid #f3f4f6', whiteSpace: 'nowrap' };
  const tdWrap: React.CSSProperties = { ...tdStyle, whiteSpace: 'normal', minWidth: 90 };
  const editInput: React.CSSProperties = { ...inputStyle, width: '100%', fontSize: '0.8rem', padding: '0.3rem 0.5rem' };
  const photoCount = item.photos?.length ?? 0;

  return (
    <>
      <tr style={{ background: '#fff' }}>
        {/* No */}
        <td style={{ ...tdStyle, color: '#9ca3af', textAlign: 'center' }}>{item.line_no}</td>
        {/* 날짜 */}
        <td style={{ ...tdStyle, color: 'var(--text-secondary)' }}>{batchDate || '-'}</td>
        {/* 업체명 */}
        <td style={{ ...tdStyle, fontWeight: 500 }}>{batchVendor || '-'}</td>
        {/* 도매처 */}
        <td style={{ ...tdStyle, color: 'var(--text-secondary)' }}>{batchWholesale || '-'}</td>
        {/* 제품명 */}
        <td style={tdWrap}>
          <div style={{ fontWeight: 500 }}>{item.item_name || '-'}</div>
        </td>
        {/* 옵션 */}
        <td style={tdWrap}>
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.78rem' }}>{item.option_text || '-'}</div>
        </td>
        {/* 바코드 */}
        <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: '0.75rem', color: '#6b7280' }}>
          {item.matched_barcode || '-'}
        </td>
        {/* 장끼수량 */}
        <td style={{ ...tdStyle, textAlign: 'center', fontWeight: 600, color: '#1d4ed8' }}>{item.janggi_qty}</td>
        {/* 실입고 */}
        <td style={{ ...tdStyle, textAlign: 'center' }}>
          <input
            type="number" min={0} value={actualQty}
            onChange={e => setActualQty(Number(e.target.value))}
            style={{ width: 52, ...inputStyle, textAlign: 'center', padding: '0.2rem 0.25rem' }}
          />
        </td>
        {/* 미입고 */}
        <td style={{ ...tdStyle, textAlign: 'center' }}>
          <input
            type="number" min={0} value={missingQty}
            onChange={e => setMissingQty(Number(e.target.value))}
            style={{ width: 52, ...inputStyle, textAlign: 'center', padding: '0.2rem 0.25rem' }}
          />
        </td>
        {/* 처리상태 */}
        <td style={{ ...tdStyle, textAlign: 'center' }}>
          <select
            value={status}
            onChange={e => setStatus(e.target.value)}
            style={{ ...inputStyle, padding: '0.2rem 0.3rem', fontSize: '0.75rem', minWidth: 72 }}
          >
            {Object.entries(ITEM_STATUS_LABELS).map(([val, lbl]) => (
              <option key={val} value={val}>{lbl}</option>
            ))}
          </select>
        </td>
        {/* 공급처상품명 */}
        <td style={tdWrap}>
          <div style={{ fontSize: '0.78rem', color: '#7c3aed', fontWeight: 600 }}>{item.matched_vendor || '-'}</div>
          <div style={{ fontSize: '0.78rem' }}>{item.matched_product || '-'}</div>
        </td>
        {/* 공급처옵션 */}
        <td style={{ ...tdStyle, color: 'var(--text-secondary)', fontSize: '0.78rem' }}>{item.matched_option || '-'}</td>
        {/* 공급처위치 */}
        <td style={{ ...tdStyle, fontSize: '0.78rem', color: '#374151' }}>{item.supplier_location || '-'}</td>
        {/* 공급처연락처 */}
        <td style={{ ...tdStyle, fontSize: '0.78rem', color: '#374151' }}>{item.supplier_contact || '-'}</td>
        {/* 작성자 */}
        <td style={{ ...tdStyle, fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{batchCreatedBy || '-'}</td>
        {/* 수정시간 */}
        <td style={{ ...tdStyle, fontSize: '0.73rem', color: '#9ca3af' }}>
          {item.updated_at ? item.updated_at.slice(0, 16).replace('T', ' ') : '-'}
        </td>
        {/* 사진 */}
        <td style={{ ...tdStyle, textAlign: 'center' }}>
          {photoCount > 0
            ? <span style={{ fontSize: '0.78rem', color: '#0f766e', background: '#f0fdfa', border: '1px solid #99f6e4', borderRadius: 4, padding: '2px 6px' }}>📷 {photoCount}</span>
            : <span style={{ fontSize: '0.75rem', color: '#d1d5db' }}>-</span>
          }
        </td>
        {/* 액션 */}
        <td style={{ ...tdStyle, textAlign: 'center' }}>
          <div style={{ display: 'flex', gap: 3, justifyContent: 'center' }}>
            <button onClick={save} disabled={saving} style={{ ...btn('#4361ee'), fontSize: '0.75rem', padding: '0.2rem 0.6rem' }}>
              {saving ? '…' : '저장'}
            </button>
            <button
              onClick={() => setEditMode(m => !m)}
              style={{ ...btn(editMode ? '#6b7280' : '#f59e0b'), fontSize: '0.73rem', padding: '0.2rem 0.5rem' }}
            >
              ✏️
            </button>
            {onDelete && (
              <button
                onClick={() => { if (confirm(`품목 "${item.item_name || item.line_no + '번'}"을 삭제하시겠습니까?`)) onDelete(); }}
                style={{ ...btn('#ef4444'), fontSize: '0.73rem', padding: '0.2rem 0.5rem' }}
              >
                🗑
              </button>
            )}
          </div>
        </td>
      </tr>
      {/* 수정 폼 인라인 */}
      {editMode && (
        <tr style={{ background: '#f0f4ff' }}>
          <td colSpan={19} style={{ padding: '0.75rem 1rem', borderBottom: '1px solid #e0e7ff' }}>
            <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#4361ee', marginBottom: 8 }}>✏️ 품목 정보 수정</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 8, marginBottom: 8 }}>
              <div>
                <div style={{ fontSize: '0.73rem', color: '#9ca3af', marginBottom: 3 }}>바코드</div>
                <input value={editForm.matched_barcode} onChange={e => setEditForm(f => ({ ...f, matched_barcode: e.target.value }))} style={editInput} placeholder="바코드" />
              </div>
              <div>
                <div style={{ fontSize: '0.73rem', color: '#9ca3af', marginBottom: 3 }}>공급처(업체명)</div>
                <input value={editForm.matched_vendor} onChange={e => setEditForm(f => ({ ...f, matched_vendor: e.target.value }))} style={editInput} placeholder="공급처" />
              </div>
              <div>
                <div style={{ fontSize: '0.73rem', color: '#9ca3af', marginBottom: 3 }}>공급처 상품명</div>
                <input value={editForm.matched_product} onChange={e => setEditForm(f => ({ ...f, matched_product: e.target.value }))} style={editInput} placeholder="공급처 상품명" />
              </div>
              <div>
                <div style={{ fontSize: '0.73rem', color: '#9ca3af', marginBottom: 3 }}>공급처 옵션</div>
                <input value={editForm.matched_option} onChange={e => setEditForm(f => ({ ...f, matched_option: e.target.value }))} style={editInput} placeholder="공급처 옵션" />
              </div>
              <div>
                <div style={{ fontSize: '0.73rem', color: '#9ca3af', marginBottom: 3 }}>공급처 위치</div>
                <input value={editForm.supplier_location} onChange={e => setEditForm(f => ({ ...f, supplier_location: e.target.value }))} style={editInput} placeholder="예) A동 3층" />
              </div>
              <div>
                <div style={{ fontSize: '0.73rem', color: '#9ca3af', marginBottom: 3 }}>공급처 연락처</div>
                <input value={editForm.supplier_contact} onChange={e => setEditForm(f => ({ ...f, supplier_contact: e.target.value }))} style={editInput} placeholder="010-0000-0000" />
              </div>
              <div>
                <div style={{ fontSize: '0.73rem', color: '#9ca3af', marginBottom: 3 }}>메모</div>
                <input value={editForm.memo} onChange={e => setEditForm(f => ({ ...f, memo: e.target.value }))} style={editInput} placeholder="메모" />
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={saveEdit} disabled={editSaving} style={{ ...btn('#4361ee'), opacity: editSaving ? 0.5 : 1 }}>
                {editSaving ? '저장 중…' : '수정 저장'}
              </button>
              <button onClick={() => setEditMode(false)} style={btnOutline}>취소</button>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ─────────────────────────────────────
// 품목 직접 추가 섹션 (BatchDetailModal 내부용)
// ─────────────────────────────────────

function AddItemSection({ token, batchId, batchVendor, onAdded }: {
  token: string;
  batchId: string;
  batchVendor: string;
  onAdded: () => void;
}) {
  const [open, setOpen] = useState(false);
  // 업체 선택
  const [vendorList, setVendorList] = useState<InboundRegisteredVendor[]>([]);
  const [aliasList, setAliasList] = useState<VendorAlias[]>([]);
  const [vendorQuery, setVendorQuery] = useState('');
  const [vendorOpen, setVendorOpen] = useState(false);
  const [selectedVendors, setSelectedVendors] = useState<string[]>([]);
  const [vendorDisplay, setVendorDisplay] = useState('');
  // 바코드 검색
  const [barcodeResults, setBarcodeResults] = useState<RepairBarcode[]>([]);
  const [barcodeQuery, setBarcodeQuery] = useState('');
  const [barcodeOpen, setBarcodeOpen] = useState(false);
  const [barcodeLoading, setBarcodeLoading] = useState(false);
  const [selectedBarcode, setSelectedBarcode] = useState<RepairBarcode | null>(null);
  const [apiSearchResults, setApiSearchResults] = useState<RepairBarcode[]>([]);
  const [apiSearchLoading, setApiSearchLoading] = useState(false);
  const apiSearchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // 폼
  const [form, setForm] = useState({ item_name: '', option_text: '', janggi_qty: 1, unit_price: '' });
  const [adding, setAdding] = useState(false);

  const vendorRef = useRef<HTMLDivElement>(null);
  const barcodeRef = useRef<HTMLDivElement>(null);

  // 업체/별칭 목록 로드
  useEffect(() => {
    if (!open) return;
    Promise.all([listInboundVendors(token), getVendorAliases(token)])
      .then(([v, a]) => {
        setVendorList(v.registered);
        setAliasList(a.aliases);
        // batch 업체와 일치하는 등록업체 자동 선택
        const matched = v.registered.find(r => r.name === batchVendor || r.aliases.includes(batchVendor));
        const aliasMatched = a.aliases.find(al => al.canonical === batchVendor);
        if (matched && !vendorDisplay) {
          setVendorDisplay(matched.name);
          setVendorQuery(matched.name);
          setSelectedVendors([matched.name]);
        } else if (aliasMatched && !vendorDisplay) {
          setVendorDisplay(aliasMatched.canonical);
          setVendorQuery(aliasMatched.canonical);
          setSelectedVendors(aliasMatched.aliases.length > 0 ? aliasMatched.aliases : [aliasMatched.canonical]);
        }
      })
      .catch(() => {});
  }, [open, token, batchVendor]);

  // 바코드 목록 로드
  useEffect(() => {
    if (selectedVendors.length === 0) { setBarcodeResults([]); return; }
    setBarcodeLoading(true);
    Promise.all(selectedVendors.map(v => getRepairBarcodes({ vendor: v, limit: 300 })))
      .then(results => {
        const seen = new Set<string>();
        setBarcodeResults(results.flatMap(r => r.items).filter(b => {
          if (seen.has(b.바코드)) return false;
          seen.add(b.바코드); return true;
        }));
      })
      .catch(() => setBarcodeResults([]))
      .finally(() => setBarcodeLoading(false));
  }, [selectedVendors]);

  // 외부 클릭 닫기
  useEffect(() => {
    function h(e: MouseEvent) {
      if (vendorRef.current && !vendorRef.current.contains(e.target as Node)) setVendorOpen(false);
      if (barcodeRef.current && !barcodeRef.current.contains(e.target as Node)) setBarcodeOpen(false);
    }
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  function selectVendor(name: string, members: string[]) {
    setVendorDisplay(name); setVendorQuery(name);
    setSelectedVendors(members.length > 0 ? members : [name]);
    setVendorOpen(false); setSelectedBarcode(null); setBarcodeQuery('');
  }

  function selectBarcode(b: RepairBarcode) {
    setSelectedBarcode(b);
    setBarcodeQuery(`${b.바코드} — ${b.제품명}${b.옵션 ? ' / ' + b.옵션 : ''}`);
    setBarcodeOpen(false); setApiSearchResults([]);
    setForm(f => ({ ...f, item_name: f.item_name || b.제품명, option_text: f.option_text || (b.옵션 || '') }));
  }

  function handleBarcodeQueryChange(val: string) {
    setBarcodeQuery(val); setBarcodeOpen(true);
    if (apiSearchTimerRef.current) clearTimeout(apiSearchTimerRef.current);
    if (!val.trim()) { setApiSearchResults([]); return; }
    // 항상 전체 API 검색 (벤더 별칭 불일치 방지)
    apiSearchTimerRef.current = setTimeout(async () => {
      setApiSearchLoading(true);
      try { const r = await getRepairBarcodes({ q: val.trim(), limit: 40 }); setApiSearchResults(r.items); }
      catch { setApiSearchResults([]); }
      finally { setApiSearchLoading(false); }
    }, 350);
  }

  const fvq = vendorQuery.toLowerCase();
  const fVendors = vendorList.filter(v => v.name.toLowerCase().includes(fvq) || v.aliases.some(a => a.toLowerCase().includes(fvq)));
  const fAliases = aliasList.filter(a => a.canonical.toLowerCase().includes(fvq) || a.aliases.some(al => al.toLowerCase().includes(fvq)));
  const fbq = (selectedBarcode ? '' : barcodeQuery).toLowerCase();
  const fBarcodes = barcodeResults.filter(b =>
    b.바코드.toLowerCase().includes(fbq) || b.제품명.toLowerCase().includes(fbq) ||
    (b.옵션 || '').toLowerCase().includes(fbq) || b.업체명.toLowerCase().includes(fbq) ||
    (b.상품명 || '').toLowerCase().includes(fbq) || (b.도매처 || '').toLowerCase().includes(fbq)
  );
  // 타이핑 중이면 API 전체검색 결과 우선
  const displayBarcodes = barcodeQuery.trim() ? apiSearchResults.slice(0, 40) : fBarcodes.slice(0, 40);

  function resetForm() {
    setForm({ item_name: '', option_text: '', janggi_qty: 1, unit_price: '' });
    setSelectedBarcode(null); setBarcodeQuery('');
  }

  async function handleAdd() {
    if (!form.item_name.trim()) return;
    setAdding(true);
    try {
      await addInboundItem(token, batchId, {
        item_name: form.item_name.trim(),
        option_text: form.option_text.trim() || undefined,
        janggi_qty: form.janggi_qty,
        unit_price: form.unit_price ? Number(form.unit_price) : undefined,
        memo: 'manual',
        matched_barcode: selectedBarcode?.바코드,
        matched_vendor: selectedBarcode?.업체명,
        matched_product: selectedBarcode?.제품명,
        matched_option: selectedBarcode?.옵션 || undefined,
      });
      resetForm();
      onAdded();
    } catch (e) {
      alert('품목 추가 실패: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setAdding(false);
    }
  }

  const inp: React.CSSProperties = { ...inputStyle, width: '100%' };
  const lbl: React.CSSProperties = { fontSize: '0.76rem', color: 'var(--text-secondary)', fontWeight: 600, marginBottom: 3, display: 'block' };
  const dropBase: React.CSSProperties = {
    position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 600,
    background: '#fff', border: '1px solid var(--border)', borderRadius: 6,
    boxShadow: '0 4px 16px rgba(0,0,0,0.12)', maxHeight: 220, overflowY: 'auto', marginTop: 2,
  };
  const grpLbl: React.CSSProperties = {
    padding: '4px 10px', fontSize: 10, color: '#9ca3af', fontWeight: 700,
    textTransform: 'uppercase', background: '#fafafa', borderBottom: '1px solid #f3f4f6',
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '0.5rem 1rem', border: '2px dashed #c7d2fe',
          background: '#eef2ff', color: '#4361ee', borderRadius: 6,
          fontSize: '0.85rem', fontWeight: 600, cursor: 'pointer', marginBottom: '0.75rem',
        }}
      >
        ➕ 품목 직접 추가
      </button>
    );
  }

  return (
    <div style={{ marginBottom: '1rem', border: '1px solid #c7d2fe', borderRadius: 8, background: '#f8faff', padding: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
        <span style={{ fontWeight: 700, fontSize: '0.9rem', color: '#4361ee' }}>➕ 품목 직접 추가</span>
        <button onClick={() => { setOpen(false); resetForm(); }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', fontSize: '1.1rem' }}>×</button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.6rem', marginBottom: '0.6rem' }}>
        {/* 업체 선택 */}
        <div ref={vendorRef} style={{ position: 'relative', gridColumn: '1 / -1' }}>
          <label style={lbl}>업체 (등록업체·별칭 검색)</label>
          <input
            value={vendorQuery}
            onChange={e => { setVendorQuery(e.target.value); setVendorOpen(true); if (!e.target.value) { setSelectedVendors([]); setVendorDisplay(''); } }}
            onFocus={() => setVendorOpen(true)}
            placeholder="업체명 또는 별칭 검색…"
            style={inp}
          />
          {vendorOpen && (fVendors.length > 0 || fAliases.length > 0) && (
            <div style={dropBase}>
              {fVendors.length > 0 && (
                <>
                  <div style={grpLbl}>📦 등록 업체</div>
                  {fVendors.map(v => (
                    <div key={v.name} onMouseDown={() => selectVendor(v.name, [v.name])}
                      style={{ padding: '7px 12px', cursor: 'pointer', fontSize: 13, background: vendorDisplay === v.name ? '#eef2ff' : undefined }}>
                      <strong>{v.name}</strong>
                      {v.aliases.length > 0 && <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 6 }}>({v.aliases.join(', ')})</span>}
                    </div>
                  ))}
                </>
              )}
              {fAliases.length > 0 && (
                <>
                  <div style={grpLbl}>🏷️ 화주사 별칭</div>
                  {fAliases.map(a => (
                    <div key={a.canonical} onMouseDown={() => selectVendor(a.canonical, a.aliases)}
                      style={{ padding: '7px 12px', cursor: 'pointer', fontSize: 13 }}>
                      <span style={{ fontWeight: 600, color: '#1d4ed8' }}>{a.canonical}</span>
                      {a.aliases.length > 0 && <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 6 }}>→ {a.aliases.join(', ')}</span>}
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>

        {/* 바코드 검색 */}
        <div ref={barcodeRef} style={{ position: 'relative', gridColumn: '1 / -1' }}>
          <label style={lbl}>
            바코드 검색{' '}
            {(barcodeLoading || apiSearchLoading) ? '(검색 중…)' : selectedVendors.length > 0 && barcodeResults.length > 0 ? `(${barcodeResults.length}개 로드됨)` : '(바코드·제품명·도매처 검색)'}
          </label>
          {selectedBarcode ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ flex: 1, padding: '0.4rem 0.65rem', background: '#ede9fe', borderRadius: 6, fontSize: '0.82rem', color: '#7c3aed', fontWeight: 500 }}>
                ✅ {selectedBarcode.바코드} — {selectedBarcode.업체명} / {selectedBarcode.제품명}{selectedBarcode.옵션 ? ' / ' + selectedBarcode.옵션 : ''}
              </div>
              <button onClick={() => { setSelectedBarcode(null); setBarcodeQuery(''); setApiSearchResults([]); }} style={{ ...btnOutline, padding: '0.3rem 0.6rem', fontSize: '0.75rem' }}>변경</button>
            </div>
          ) : (
            <>
              <input
                value={barcodeQuery}
                onChange={e => handleBarcodeQueryChange(e.target.value)}
                onFocus={() => barcodeQuery && setBarcodeOpen(true)}
                placeholder={selectedVendors.length > 0 && barcodeResults.length > 0
                  ? `바코드·제품명·도매처 검색 (${barcodeResults.length}개 중)`
                  : '바코드번호, 제품명, 상품명, 도매처 검색'}
                style={inp}
              />
              {barcodeOpen && displayBarcodes.length > 0 && (
                <div style={dropBase}>
                  {displayBarcodes.map(b => (
                    <div key={b.바코드} onMouseDown={() => selectBarcode(b)}
                      style={{ padding: '8px 12px', cursor: 'pointer', borderBottom: '1px solid #f3f4f6' }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: '#111827' }}>
                        {b.제품명}{b.옵션 ? ` / ${b.옵션}` : ''}
                      </div>
                      {b.상품명 && b.상품명 !== b.제품명 && (
                        <div style={{ fontSize: 11, color: '#6b7280', marginTop: 1 }}>{b.상품명}</div>
                      )}
                      <div style={{ fontSize: 11, color: '#9ca3af', display: 'flex', gap: 8, marginTop: 2, fontFamily: 'monospace' }}>
                        <span>{b.바코드}</span>
                        {b.도매처 && <span style={{ color: '#7c3aed', fontFamily: 'inherit' }}>{b.도매처}</span>}
                        {b.업체명 && <span style={{ color: '#9ca3af', fontFamily: 'inherit' }}>[{b.업체명}]</span>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {!barcodeLoading && !apiSearchLoading && barcodeQuery.trim() && displayBarcodes.length === 0 && (
                <div style={{ fontSize: '0.78rem', color: '#9ca3af', padding: '4px 2px' }}>검색 결과 없음</div>
              )}
            </>
          )}
        </div>

        {/* 품명 */}
        <div style={{ gridColumn: '1 / -1' }}>
          <label style={lbl}>품명 *</label>
          <input value={form.item_name} onChange={e => setForm(f => ({ ...f, item_name: e.target.value }))} placeholder="예) 타원 백팩" style={inp} />
        </div>

        {/* 옵션 */}
        <div>
          <label style={lbl}>옵션</label>
          <input value={form.option_text} onChange={e => setForm(f => ({ ...f, option_text: e.target.value }))} placeholder="블랙, L" style={inp} />
        </div>

        {/* 장끼 수량 */}
        <div>
          <label style={lbl}>장끼 수량 *</label>
          <input type="number" min={1} value={form.janggi_qty} onChange={e => setForm(f => ({ ...f, janggi_qty: Number(e.target.value) }))}
            style={{ ...inp, textAlign: 'center', fontWeight: 700, fontSize: '1rem' }} />
        </div>

        {/* 단가 */}
        <div style={{ gridColumn: '1 / -1' }}>
          <label style={lbl}>단가 (선택)</label>
          <input type="number" min={0} value={form.unit_price} onChange={e => setForm(f => ({ ...f, unit_price: e.target.value }))}
            placeholder="0" style={{ ...inp, maxWidth: 160 }} />
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <button onClick={() => { setOpen(false); resetForm(); }} style={btnOutline}>취소</button>
        <button
          onClick={handleAdd}
          disabled={adding || !form.item_name.trim()}
          style={{ ...btn('#4361ee'), opacity: (adding || !form.item_name.trim()) ? 0.5 : 1 }}
        >
          {adding ? '추가 중…' : '➕ 추가'}
        </button>
      </div>
    </div>
  );
}

// ─────────────────────────────────────
// 배치 상세 모달
// ─────────────────────────────────────

function BatchDetailModal({ batch: initialBatch, token, onClose, onUpdated }: {
  batch: InboundBatch; token: string; onClose: () => void; onUpdated: () => void;
}) {
  const [batch, setBatch] = useState<InboundBatch>(initialBatch);
  const [ocrFile, setOcrFile] = useState<File | null>(null);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [closeLoading, setCloseLoading] = useState(false);
  const [warning, setWarning] = useState('');
  const [pdfLoading, setPdfLoading] = useState(false);
  const [shareLink, setShareLink] = useState('');
  const [shareLoading, setShareLoading] = useState(false);
  const [sharePassword, setSharePassword] = useState('');
  const [sharePasswordOpen, setSharePasswordOpen] = useState(false);
  // 비밀번호 1회 표시: 생성 직후에만 보이고, 확인 버튼 누르면 소멸
  const [shownPasswordOnce, setShownPasswordOnce] = useState('');
  const [closeSummary, setCloseSummary] = useState<{
    total_janggi_qty: number;
    정상_qty: number; 수선중_qty: number; 수선후정상_qty: number;
    회생불가_qty: number; 미입고_qty: number;
    formula_ok: boolean; formula_str: string; discrepancy: number;
  } | null>(null);

  const reload = useCallback(async () => {
    const data = await getInboundBatch(token, batch.id);
    setBatch(data);
  }, [token, batch.id]);

  async function handleOcr() {
    if (!ocrFile) return;
    setOcrLoading(true); setWarning('');
    try {
      const res = await runInboundOcr(token, batch.id, ocrFile);
      await reload();
      alert(`OCR 완료: ${res.item_count}개 품목 (자동매칭 ${res.matched_count}개 / 확인필요 ${res.needs_matching_count}개)`);
    } catch (e: unknown) {
      alert('OCR 실패: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setOcrLoading(false);
    }
  }

  async function handlePdf() {
    setPdfLoading(true);
    try {
      await downloadInboundBarcodePdf(token, batch.id, batch.vendor, batch.inbound_date);
    } catch (e: unknown) {
      alert('PDF 실패: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setPdfLoading(false);
    }
  }

  async function handleShare() {
    setShareLoading(true);
    try {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const res = await fetch(`${API_BASE}/inbound/batches/${batch.id}/share`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expires_days: 14,
          allow_excel: false,
          password: sharePassword.trim() || null,
        }),
      });
      const data = await res.json();
      setShareLink(data.link);
      // 비밀번호 원문 — 생성 응답에서 한 번만 받아 표시
      setShownPasswordOnce(data.password_once || '');
      setSharePassword('');      // 입력창 즉시 초기화
      setSharePasswordOpen(false);
    } catch (e: unknown) {
      alert('공유 링크 생성 실패: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setShareLoading(false);
    }
  }

  async function handleClose(closeType: 'am' | 'pm') {
    setCloseLoading(true); setWarning(''); setCloseSummary(null);
    try {
      const res = await closeInboundBatch(token, batch.id, closeType);
      if (!res.ok && res.warning) {
        setWarning(res.warning);
      } else {
        // PM 마감이면 정산 데이터 저장
        if (closeType === 'pm' && res.close_type === 'pm') {
          setCloseSummary({
            total_janggi_qty: res.total_janggi_qty ?? 0,
            정상_qty:          res.정상_qty ?? 0,
            수선중_qty:         res.수선중_qty ?? 0,
            수선후정상_qty:     res.수선후정상_qty ?? 0,
            회생불가_qty:       res.회생불가_qty ?? 0,
            미입고_qty:         res.미입고_qty ?? 0,
            formula_ok:        res.formula_ok ?? true,
            formula_str:       res.formula_str ?? '',
            discrepancy:       res.discrepancy ?? 0,
          });
        }
        await reload();
        onUpdated();
      }
    } catch (e: unknown) {
      alert('마감 실패: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setCloseLoading(false);
    }
  }

  const items = batch.items || [];
  // AM/PM 버튼은 JSX에서 batch.status 조건으로 직접 분기

  const statBox = (label: string, value: number, color: string) => (
    <div style={{ textAlign: 'center', padding: '0.5rem 1rem', background: '#f8f9fc', borderRadius: 8 }}>
      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: '1.3rem', fontWeight: 700, color }}>{value}</div>
    </div>
  );

  return (
    <Modal title={`입고 상세 — ${batch.vendor} / ${batch.inbound_date}`} onClose={onClose} wide>
      {/* 헤더 요약 */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'center', marginBottom: '1rem' }}>
        <StatusBadge status={batch.status} label={batch.status_label} map={STATUS_COLOR} />
        {batch.wholesale && (
          <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            도매처: <strong>{batch.wholesale}</strong>
          </span>
        )}
        {batch.janggi_no && (
          <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>장끼번호: {batch.janggi_no}</span>
        )}
        {batch.janggi_date && (
          <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>장끼일자: {batch.janggi_date}</span>
        )}
      </div>

      {/* 수량 요약 */}
      <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.25rem', flexWrap: 'wrap' }}>
        {statBox('장끼수량', batch.total_janggi_qty, '#1d4ed8')}
        {statBox('실입고', batch.total_actual_qty, '#15803d')}
        {statBox('미입고', batch.total_missing_qty, '#dc2626')}
      </div>

      {/* 장끼 OCR 영역 */}
      {['ocr_pending', 'confirming'].includes(batch.status) && (
        <div style={{
          marginBottom: '1rem', padding: '0.85rem 1rem',
          background: '#fef9c3', borderRadius: 8, border: '1px solid #fde047',
        }}>
          <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#a16207', marginBottom: '0.5rem' }}>
            {batch.status === 'ocr_pending' ? '📄 장끼 사진을 업로드해주세요' : '🔄 장끼 재분석'}
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <input
              type="file" accept="image/*"
              onChange={e => setOcrFile(e.target.files?.[0] || null)}
              style={{ fontSize: '0.82rem' }}
            />
            <button
              onClick={handleOcr}
              disabled={!ocrFile || ocrLoading}
              style={{ ...btn('#a16207'), opacity: (!ocrFile || ocrLoading) ? 0.5 : 1 }}
            >
              {ocrLoading ? 'AI 분석 중…' : 'OCR 실행'}
            </button>
          </div>
        </div>
      )}

      {/* 경고 */}
      {warning && (
        <div style={{
          marginBottom: '0.75rem', padding: '0.75rem 1rem',
          background: '#fef2f2', border: '1px solid #fecaca',
          borderRadius: 6, fontSize: '0.85rem', color: '#dc2626',
        }}>
          ⚠️ {warning}
        </div>
      )}

      {/* 품목 직접 추가 섹션 */}
      <AddItemSection
        token={token}
        batchId={batch.id}
        batchVendor={batch.vendor}
        onAdded={reload}
      />

      {/* 품목 테이블 */}
      {items.length > 0 ? (
        <div style={{ overflowX: 'auto', marginBottom: '1rem' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
            <thead>
              <tr style={{ background: '#f8f9fc' }}>
                {[
                  { label: 'No', align: 'center' },
                  { label: '날짜', align: 'left' },
                  { label: '업체명', align: 'left' },
                  { label: '도매처', align: 'left' },
                  { label: '제품명', align: 'left' },
                  { label: '옵션', align: 'left' },
                  { label: '바코드', align: 'left' },
                  { label: '장끼수량', align: 'center' },
                  { label: '실입고', align: 'center' },
                  { label: '미입고', align: 'center' },
                  { label: '처리상태', align: 'center' },
                  { label: '공급처상품명', align: 'left' },
                  { label: '공급처옵션', align: 'left' },
                  { label: '공급처위치', align: 'left' },
                  { label: '공급처연락처', align: 'left' },
                  { label: '작성자', align: 'left' },
                  { label: '수정시간', align: 'left' },
                  { label: '사진', align: 'center' },
                  { label: '', align: 'center' },
                ].map(h => (
                  <th key={h.label} style={{ padding: '0.55rem 0.6rem', fontSize: '0.72rem', color: 'var(--text-secondary)', fontWeight: 600, textAlign: h.align as 'left' | 'center', borderBottom: '1px solid var(--border)', whiteSpace: 'nowrap', background: '#f8f9fc', position: 'sticky', top: 0, zIndex: 1 }}>
                    {h.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.map(item => (
                <ItemRow
                  key={item.id}
                  item={item}
                  token={token}
                  onUpdated={reload}
                  batchVendor={batch.vendor}
                  batchDate={batch.inbound_date}
                  batchWholesale={batch.wholesale}
                  batchCreatedBy={batch.created_by}
                  onDelete={async () => {
                    try {
                      await deleteInboundItem(token, item.id);
                      await reload();
                    } catch (e) {
                      alert('삭제 실패: ' + (e instanceof Error ? e.message : String(e)));
                    }
                  }}
                />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)', fontSize: '0.875rem', background: '#f8f9fc', borderRadius: 8, marginBottom: '1rem' }}>
          <div style={{ fontSize: '1.5rem', marginBottom: 8 }}>📋</div>
          <div>품목이 없습니다.</div>
          <div style={{ fontSize: '0.8rem', color: '#9ca3af', marginTop: 4 }}>위 "품목 직접 추가" 버튼으로 추가하거나, 장끼 사진 OCR을 실행하세요.</div>
        </div>
      )}

      {/* ── 오후 마감 정산 결과 ─────────── */}
      {closeSummary && (
        <div style={{ marginBottom: '0.75rem', padding: '0.9rem 1rem', background: closeSummary.formula_ok ? '#f0f9ff' : '#fff7ed', border: `1px solid ${closeSummary.formula_ok ? '#bae6fd' : '#fed7aa'}`, borderRadius: 8, fontSize: '0.85rem' }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>📊 오후 최종 마감 정산</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
            {[
              { label: '장끼수량',   qty: closeSummary.total_janggi_qty, color: '#1d4ed8', bg: '#dbeafe' },
              { label: '일반정상',   qty: closeSummary.정상_qty,          color: '#15803d', bg: '#dcfce7' },
              { label: '수선중',     qty: closeSummary.수선중_qty,         color: '#a16207', bg: '#fef9c3' },
              { label: '수선후정상', qty: closeSummary.수선후정상_qty,     color: '#166534', bg: '#bbf7d0' },
              { label: '회생불가',   qty: closeSummary.회생불가_qty,       color: '#991b1b', bg: '#fecaca' },
              { label: '미입고',     qty: closeSummary.미입고_qty,         color: '#dc2626', bg: '#fee2e2' },
            ].map(s => (
              <div key={s.label} style={{ background: s.bg, borderRadius: 8, padding: '6px 12px', textAlign: 'center', minWidth: 68 }}>
                <div style={{ fontSize: '0.7rem', color: s.color, fontWeight: 700 }}>{s.label}</div>
                <div style={{ fontSize: '1.2rem', fontWeight: 800, color: s.color }}>{s.qty}<span style={{ fontSize: '0.68rem' }}>개</span></div>
              </div>
            ))}
          </div>
          <div style={{ fontSize: '0.78rem', color: closeSummary.formula_ok ? '#0369a1' : '#c2410c', fontFamily: 'monospace', background: closeSummary.formula_ok ? '#e0f2fe' : '#fff7ed', padding: '5px 8px', borderRadius: 5 }}>
            {closeSummary.formula_str}
          </div>
          {!closeSummary.formula_ok && (
            <div style={{ marginTop: 6, fontSize: '0.8rem', color: '#c2410c', fontWeight: 600 }}>
              ⚠️ 수량 합계가 맞지 않습니다. 품목 수량을 다시 확인해주세요.
            </div>
          )}
        </div>
      )}

      {/* ── 공유 링크 비밀번호 입력 ─────── */}
      {sharePasswordOpen && (
        <div style={{ marginBottom: '0.75rem', padding: '0.85rem 1rem', background: '#faf5ff', border: '1px solid #e9d5ff', borderRadius: 8 }}>
          <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: 6, color: '#7c3aed' }}>🔒 공유 링크 비밀번호 (선택)</div>
          <div style={{ fontSize: '0.78rem', color: '#6b7280', marginBottom: 8 }}>
            비밀번호를 설정하면 화주사가 링크를 열 때 입력해야 합니다.<br />
            <strong>생성 후 비밀번호는 아래에 딱 한 번만 표시됩니다.</strong>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <input
              type="text"
              value={sharePassword}
              onChange={e => setSharePassword(e.target.value)}
              placeholder="비밀번호 없으면 비워두세요"
              style={{ ...inputStyle, flex: 1 }}
            />
            <button onClick={handleShare} disabled={shareLoading} style={{ ...btn('#7c3aed'), opacity: shareLoading ? 0.5 : 1 }}>
              {shareLoading ? '생성 중…' : '링크 생성'}
            </button>
            <button onClick={() => { setSharePasswordOpen(false); setSharePassword(''); }} style={btnOutline}>취소</button>
          </div>
        </div>
      )}

      {/* ── 공유 링크 1회 비밀번호 표시 ─── */}
      {shareLink && shownPasswordOnce && (
        <div style={{ marginBottom: '0.75rem', padding: '0.9rem 1rem', background: '#fefce8', border: '2px solid #fde047', borderRadius: 8, fontSize: '0.85rem' }}>
          <div style={{ fontWeight: 700, color: '#a16207', marginBottom: 6 }}>🔐 비밀번호 (지금만 표시 — 저장해두세요)</div>
          <div style={{ fontSize: '1.4rem', fontWeight: 800, letterSpacing: '0.15em', color: '#92400e', fontFamily: 'monospace', marginBottom: 8 }}>
            {shownPasswordOnce}
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              onClick={() => { navigator.clipboard.writeText(shownPasswordOnce); alert('비밀번호를 클립보드에 복사했습니다.'); }}
              style={{ ...btn('#a16207'), fontSize: '0.8rem' }}
            >
              복사
            </button>
            <button
              onClick={() => setShownPasswordOnce('')}
              style={{ ...btnOutline, fontSize: '0.8rem', color: '#dc2626', borderColor: '#dc2626' }}
            >
              확인했습니다 (닫기)
            </button>
          </div>
        </div>
      )}

      {/* ── 공유 링크 표시 ─────────────── */}
      {shareLink && (
        <div style={{ marginBottom: '0.75rem', padding: '0.75rem 1rem', background: '#f0fff4', border: '1px solid #bbf7d0', borderRadius: 6, fontSize: '0.85rem' }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>🔗 화주사 공유 링크 (14일 유효)</div>
          <div style={{ wordBreak: 'break-all', color: '#4361ee', marginBottom: 6 }}>{shareLink}</div>
          <button onClick={() => { navigator.clipboard.writeText(shareLink); }} style={{ fontSize: '0.78rem', ...btnOutline }}>링크 복사</button>
        </div>
      )}

      {/* ── PDF + 공유 버튼 ────────────── */}
      {(() => {
        const totalLabels = items.reduce((s, i) => s + (i.actual_qty || 0), 0);
        const matchedItems = items.filter(i => i.actual_qty > 0 && i.matched_barcode).length;
        return (
          <div style={{ marginBottom: '0.75rem' }}>
            {totalLabels > 0 && (
              <div style={{ fontSize: '0.8rem', color: '#0f766e', background: '#f0fdfa', border: '1px solid #99f6e4', borderRadius: 6, padding: '5px 10px', marginBottom: 6 }}>
                🏷️ 라벨 예상 <strong>{totalLabels}장</strong> (바코드 매칭 품목 {matchedItems}건)
              </div>
            )}
            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
              <button onClick={handlePdf} disabled={pdfLoading} style={{ ...btn('#0f766e'), opacity: pdfLoading ? 0.5 : 1 }}>
                {pdfLoading ? '생성 중…' : `📄 바코드 PDF${totalLabels > 0 ? ` (${totalLabels}장)` : ''}`}
              </button>
              <button
                onClick={() => { setSharePasswordOpen(true); setShareLink(''); setShownPasswordOnce(''); }}
                disabled={shareLoading}
                style={{ ...btn('#7c3aed'), opacity: shareLoading ? 0.5 : 1 }}
              >
                🔗 화주사 공유 링크
              </button>
            </div>
          </div>
        );
      })()}

      {/* ── AM / PM 마감 버튼 ─────────── */}
      <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
        {/* 오전: confirming 상태에서만 */}
        {batch.status === 'confirming' && (
          <button
            onClick={() => handleClose('am')}
            disabled={closeLoading}
            style={{ ...btn('#0369a1'), opacity: closeLoading ? 0.5 : 1 }}
            title="수량 확인 완료 후 양품화 단계로 진행"
          >
            {closeLoading ? '처리 중…' : '☀️ 오전 입고접수 완료'}
          </button>
        )}
        {/* 오후: inbound_done / grading / repairing 상태에서만 */}
        {['inbound_done', 'grading', 'repairing'].includes(batch.status) && (
          <button
            onClick={() => handleClose('pm')}
            disabled={closeLoading}
            style={{ ...btn('#7c3aed'), opacity: closeLoading ? 0.5 : 1 }}
            title="양품화 및 수선 완료 후 최종 수량 확정"
          >
            {closeLoading ? '처리 중…' : '🌆 오후 최종 마감'}
          </button>
        )}
      </div>
    </Modal>
  );
}

// ─────────────────────────────────────
// 벤더 콤보박스 컴포넌트
// ─────────────────────────────────────

interface VendorComboboxProps {
  token: string;
  value: string;                           // 표시 텍스트
  canonical: string | null;               // 선택된 등록 업체 (null = 직접입력)
  onChange: (display: string, canonical: string | null) => void;
}

function VendorCombobox({ token, value, canonical, onChange }: VendorComboboxProps) {
  const [registered, setRegistered] = useState<InboundRegisteredVendor[]>([]);
  const [recent, setRecent] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(value);
  const [aliasModal, setAliasModal] = useState<InboundRegisteredVendor | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listInboundVendors(token)
      .then(r => { setRegistered(r.registered); setRecent(r.recent); })
      .catch(() => {});
  }, [token]);

  // 바깥 클릭 시 닫기
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, []);

  // query → 부모에 반영 (직접입력 모드)
  function handleInput(v: string) {
    setQuery(v);
    onChange(v, null);  // canonical = null → 직접입력
    setOpen(true);
  }

  // 등록 업체 선택
  function selectRegistered(v: InboundRegisteredVendor) {
    setQuery(v.name);
    onChange(v.name, v.name);
    setOpen(false);
  }

  // 최근 업체 선택
  function selectRecent(v: string) {
    setQuery(v);
    onChange(v, null);
    setOpen(false);
  }

  // 필터링
  const q = query.toLowerCase();
  const filteredReg = registered.filter(v =>
    v.name.toLowerCase().includes(q) ||
    v.aliases.some(a => a.toLowerCase().includes(q))
  );
  const filteredRecent = recent.filter(v => v.toLowerCase().includes(q));

  const dropW: React.CSSProperties = {
    position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 200,
    background: '#fff', border: '1px solid #d1d5db', borderRadius: 6,
    boxShadow: '0 4px 12px rgba(0,0,0,0.12)', maxHeight: 260, overflowY: 'auto',
    marginTop: 2,
  };
  const groupLbl: React.CSSProperties = {
    padding: '4px 10px', fontSize: 11, color: '#9ca3af',
    fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em',
    borderBottom: '1px solid #f3f4f6', background: '#fafafa',
  };
  const optItem: React.CSSProperties = {
    padding: '7px 12px', cursor: 'pointer', fontSize: 13,
    display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
  };

  return (
    <div ref={wrapRef} style={{ position: 'relative', width: '100%' }}>
      <div style={{ display: 'flex', gap: 4 }}>
        <input
          value={query}
          onChange={e => handleInput(e.target.value)}
          onFocus={() => setOpen(true)}
          placeholder="업체명 검색 또는 직접 입력"
          style={{ ...inputStyle, flex: 1 }}
          autoComplete="off"
        />
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          style={{ ...btnOutline, padding: '0 10px', minWidth: 32, fontSize: 12 }}
          title="목록 열기"
        >▾</button>
      </div>

      {/* 선택된 등록업체 뱃지 */}
      {canonical && (
        <div style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 11, color: 'var(--color-brand)', background: '#ede9fe', borderRadius: 4, padding: '2px 7px' }}>
            📦 등록업체: {canonical}
          </span>
          <button
            type="button"
            style={{ fontSize: 11, color: '#6b7280', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
            onClick={() => setAliasModal(registered.find(r => r.name === canonical) ?? { name: canonical, aliases: [] })}
            title="별칭 관리"
          >✎ 별칭</button>
        </div>
      )}

      {open && (filteredReg.length > 0 || filteredRecent.length > 0 || query) && (
        <div style={dropW}>
          {/* 등록 업체 섹션 */}
          {filteredReg.length > 0 && (
            <>
              <div style={groupLbl}>📦 바코드 등록 업체</div>
              {filteredReg.map(v => (
                <div
                  key={v.name}
                  style={{ ...optItem, background: v.name === canonical ? '#ede9fe' : undefined }}
                  onMouseDown={() => selectRegistered(v)}
                >
                  <div>
                    <span style={{ fontWeight: 500 }}>{v.name}</span>
                    {v.aliases.length > 0 && (
                      <span style={{ marginLeft: 6, fontSize: 11, color: '#9ca3af' }}>
                        ({v.aliases.join(', ')})
                      </span>
                    )}
                  </div>
                  {v.name === canonical && <span style={{ color: 'var(--color-brand)', fontSize: 12 }}>✓</span>}
                </div>
              ))}
            </>
          )}
          {/* 최근 사용 섹션 */}
          {filteredRecent.length > 0 && (
            <>
              <div style={groupLbl}>🕐 최근 입고</div>
              {filteredRecent.map(v => (
                <div key={v} style={optItem} onMouseDown={() => selectRecent(v)}>
                  <span>{v}</span>
                </div>
              ))}
            </>
          )}
          {/* 직접입력 안내 */}
          {query && !filteredReg.find(v => v.name === query) && !filteredRecent.includes(query) && (
            <>
              <div style={groupLbl}>✏ 직접입력</div>
              <div style={{ ...optItem, color: '#374151' }} onMouseDown={() => { onChange(query, null); setOpen(false); }}>
                &quot;{query}&quot; 로 직접 입력
              </div>
            </>
          )}
        </div>
      )}

      {/* 별칭 관리 미니 모달 */}
      {aliasModal && (
        <AliasEditor
          token={token}
          vendor={aliasModal}
          onClose={() => setAliasModal(null)}
          onSaved={(newAliases) => {
            setRegistered(prev => prev.map(v => v.name === aliasModal.name ? { ...v, aliases: newAliases } : v));
            setAliasModal(null);
          }}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────
// 별칭 편집기 미니 모달
// ─────────────────────────────────────

function AliasEditor({ token, vendor, onClose, onSaved }: {
  token: string;
  vendor: InboundRegisteredVendor;
  onClose: () => void;
  onSaved: (aliases: string[]) => void;
}) {
  const [aliases, setAliases] = useState(vendor.aliases.join(', '));
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      const list = aliases.split(',').map(a => a.trim()).filter(Boolean);
      await upsertVendorAlias(token, vendor.name, list);
      onSaved(list);
    } catch { alert('저장 실패'); }
    finally { setSaving(false); }
  }

  const overlay: React.CSSProperties = {
    position: 'fixed', inset: 0, zIndex: 500, display: 'flex',
    alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.4)',
  };
  const box: React.CSSProperties = {
    background: '#fff', borderRadius: 10, padding: '1.5rem',
    width: 340, boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
  };

  return (
    <div style={overlay} onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={box} onMouseDown={e => e.stopPropagation()}>
        <div style={{ fontWeight: 700, fontSize: 14, marginBottom: '0.75rem' }}>
          ✎ &quot;{vendor.name}&quot; 별칭 관리
        </div>
        <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 8 }}>
          쉼표로 구분. OCR이 별칭으로 읽어도 이 업체 바코드 목록에서 매칭합니다.
        </div>
        <textarea
          value={aliases}
          onChange={e => setAliases(e.target.value)}
          placeholder="예: ABC코리아, 에이비씨, ABC"
          rows={3}
          style={{ ...inputStyle, width: '100%', resize: 'vertical' }}
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12 }}>
          <button onClick={onClose} style={btnOutline}>취소</button>
          <button onClick={save} disabled={saving} style={{ ...btn('var(--color-brand)'), opacity: saving ? 0.6 : 1 }}>
            {saving ? '저장 중…' : '저장'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────
// 신규 입고 등록 모달
// ─────────────────────────────────────

function CreateBatchModal({ token, onClose, onCreated }: {
  token: string; onClose: () => void; onCreated: (batch: InboundBatch) => void;
}) {
  const [vendor, setVendor] = useState('');
  const [vendorCanonical, setVendorCanonical] = useState<string | null>(null);
  const [inboundDate, setInboundDate] = useState(todayStr());
  const [memo, setMemo] = useState('');
  const [saving, setSaving] = useState(false);

  async function handleCreate() {
    if (!vendor.trim()) { alert('화주사를 입력해주세요.'); return; }
    setSaving(true);
    try {
      const res = await createInboundBatch(token, {
        vendor: vendor.trim(),
        vendor_canonical: vendorCanonical ?? undefined,
        inbound_date: inboundDate,
        memo: memo.trim() || undefined,
      });
      const newBatch = await getInboundBatch(token, res.id);
      onCreated(newBatch);
    } catch (e: unknown) {
      alert('생성 실패: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setSaving(false);
    }
  }

  const fRow: React.CSSProperties = { marginBottom: '1rem' };

  return (
    <Modal title="신규 입고 등록" onClose={onClose}>
      <div>
        <div style={fRow}>
          <label style={labelStyle}>화주사 *</label>
          <VendorCombobox
            token={token}
            value={vendor}
            canonical={vendorCanonical}
            onChange={(display, can) => { setVendor(display); setVendorCanonical(can); }}
          />
        </div>
        <div style={fRow}>
          <label style={labelStyle}>입고일 *</label>
          <input type="date" value={inboundDate} onChange={e => setInboundDate(e.target.value)} style={inputStyle} />
        </div>
        <div style={fRow}>
          <label style={labelStyle}>메모 (선택)</label>
          <input
            value={memo} onChange={e => setMemo(e.target.value)}
            placeholder="메모"
            style={{ ...inputStyle, width: '100%' }}
          />
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', paddingTop: '0.5rem' }}>
          <button onClick={onClose} style={btnOutline}>취소</button>
          <button onClick={handleCreate} disabled={saving} style={{ ...btn('var(--color-brand)'), opacity: saving ? 0.5 : 1 }}>
            {saving ? '생성 중…' : '입고 시작'}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ─────────────────────────────────────
// 배치 수정 모달
// ─────────────────────────────────────

function EditBatchModal({ batch, token, onClose, onUpdated }: {
  batch: InboundBatch; token: string; onClose: () => void; onUpdated: () => void;
}) {
  const [vendor, setVendor] = useState(batch.vendor);
  const [inboundDate, setInboundDate] = useState(batch.inbound_date);
  const [memo, setMemo] = useState(batch.memo || '');
  const [wholesale, setWholesale] = useState(batch.wholesale || '');
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    try {
      await updateInboundBatch(token, batch.id, {
        vendor: vendor.trim(),
        inbound_date: inboundDate,
        memo: memo.trim() || undefined,
      });
      onUpdated();
      onClose();
    } catch (e: unknown) {
      alert('수정 실패: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setSaving(false);
    }
  }

  const fRow: React.CSSProperties = { marginBottom: '1rem' };

  return (
    <Modal title="입고 정보 수정" onClose={onClose}>
      <div>
        <div style={fRow}>
          <label style={labelStyle}>화주사</label>
          <input
            value={vendor} onChange={e => setVendor(e.target.value)}
            style={{ ...inputStyle, width: '100%' }}
          />
        </div>
        <div style={fRow}>
          <label style={labelStyle}>입고일</label>
          <input type="date" value={inboundDate} onChange={e => setInboundDate(e.target.value)} style={inputStyle} />
        </div>
        <div style={fRow}>
          <label style={labelStyle}>도매처</label>
          <input
            value={wholesale} onChange={e => setWholesale(e.target.value)}
            placeholder="도매처 이름"
            style={{ ...inputStyle, width: '100%' }}
          />
        </div>
        <div style={fRow}>
          <label style={labelStyle}>메모</label>
          <input
            value={memo} onChange={e => setMemo(e.target.value)}
            placeholder="메모"
            style={{ ...inputStyle, width: '100%' }}
          />
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', paddingTop: '0.5rem' }}>
          <button onClick={onClose} style={btnOutline}>취소</button>
          <button onClick={handleSave} disabled={saving} style={{ ...btn('#f59e0b'), opacity: saving ? 0.5 : 1 }}>
            {saving ? '저장 중…' : '수정 저장'}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ─────────────────────────────────────
// 메인 페이지
// ─────────────────────────────────────

export default function InboundLogPage() {
  const [token, setToken] = useState('');
  const [batches, setBatches] = useState<InboundBatch[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [selectedBatch, setSelectedBatch] = useState<InboundBatch | null>(null);
  const [editingBatch, setEditingBatch] = useState<InboundBatch | null>(null);

  const [filterVendor, setFilterVendor] = useState('');
  const [filterWholesale, setFilterWholesale] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo] = useState('');
  const [vendorOptions, setVendorOptions] = useState<string[]>([]);
  const [wholesaleOptions, setWholesaleOptions] = useState<string[]>([]);
  const [aliasGroups, setAliasGroups] = useState<InboundAliasGroup[]>([]);
  const [filterAlias, setFilterAlias] = useState('');

  useEffect(() => { setToken(localStorage.getItem('token') || ''); }, []);

  const load = useCallback(async (tok: string) => {
    if (!tok) return;
    setLoading(true);
    try {
      const res = await listInboundBatches(tok, {
        vendor: filterAlias || filterVendor || undefined,
        wholesale: filterWholesale || undefined,
        status: filterStatus || undefined,
        dateFrom: filterDateFrom || undefined,
        dateTo: filterDateTo || undefined,
      });
      setBatches(res.items);
      setTotal(res.total);
    } catch {
      //
    } finally {
      setLoading(false);
    }
  }, [filterVendor, filterAlias, filterWholesale, filterStatus, filterDateFrom, filterDateTo]);

  useEffect(() => {
    if (!token) return;
    getInboundFilterOptions(token)
      .then(r => { setVendorOptions(r.vendors); setWholesaleOptions(r.wholesales); setAliasGroups(r.alias_groups ?? []); })
      .catch(() => {});
  }, [token]);

  useEffect(() => { if (token) load(token); }, [token, load]);

  function refreshFilterOptions(tok: string) {
    getInboundFilterOptions(tok)
      .then(r => { setVendorOptions(r.vendors); setWholesaleOptions(r.wholesales); setAliasGroups(r.alias_groups ?? []); })
      .catch(() => {});
  }

  async function openDetail(batch: InboundBatch) {
    try {
      const detail = await getInboundBatch(token, batch.id);
      setSelectedBatch(detail);
    } catch {
      setMessage({ type: 'error', text: '상세 정보를 불러오지 못했습니다.' });
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('이 입고건을 삭제하시겠습니까?')) return;
    try {
      await deleteInboundBatch(token, id);
      load(token);
      setMessage({ type: 'success', text: '삭제되었습니다.' });
    } catch (e: unknown) {
      setMessage({ type: 'error', text: (e instanceof Error ? e.message : String(e)) });
    }
  }

  const thStyle: React.CSSProperties = {
    padding: '0.65rem 1rem', fontSize: '0.78rem', fontWeight: 600,
    color: 'var(--text-secondary)', background: '#f8f9fc',
    borderBottom: '1px solid var(--border)', whiteSpace: 'nowrap',
  };
  const tdStyle: React.CSSProperties = {
    padding: '0.7rem 1rem', fontSize: '0.85rem', verticalAlign: 'middle',
    borderBottom: '1px solid #f3f4f6',
  };

  return (
    <div style={{ padding: '1.5rem' }}>
      {/* 타이틀 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem', paddingBottom: '1rem', borderBottom: '1px solid var(--border)' }}>
        <div>
          <h1 style={{ fontSize: '1.375rem', fontWeight: 700, color: 'var(--text-primary)' }}>📦 입고일지</h1>
          <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
            장끼 OCR → 상품 매칭 → 실수량 확인 → 양품화 → 마감
          </p>
        </div>
        <button onClick={() => setShowCreate(true)} style={btn('var(--color-brand)')}>
          + 입고 등록
        </button>
      </div>

      {message && <Alert type={message.type} message={message.text} onClose={() => setMessage(null)} />}

      {/* 필터 */}
      <Card style={{ marginBottom: '1rem', padding: '0.85rem 1rem' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.6rem', alignItems: 'flex-end' }}>
          {/* 화주사 셀렉트박스 */}
          <div>
            <label style={labelStyle}>화주사 (업체명)</label>
            <select
              value={filterVendor}
              onChange={e => { setFilterVendor(e.target.value); setFilterAlias(''); }}
              style={{ ...inputStyle, width: 150 }}
            >
              <option value="">전체</option>
              {vendorOptions.map(v => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </div>
          {/* 별칭 셀렉트박스 */}
          <div>
            <label style={labelStyle}>
              화주사 (별칭)
              <span style={{ fontSize: '0.68rem', fontWeight: 400, color: '#9ca3af', marginLeft: 4 }}>일지설정 기준</span>
            </label>
            <select
              value={filterAlias}
              onChange={e => { setFilterAlias(e.target.value); setFilterVendor(''); }}
              style={{ ...inputStyle, width: 160 }}
            >
              <option value="">전체</option>
              {aliasGroups.map(g =>
                g.aliases.map(alias => (
                  <option key={`${g.canonical}__${alias}`} value={alias}>
                    {alias} ({g.canonical})
                  </option>
                ))
              )}
            </select>
          </div>
          {/* 도매처 셀렉트박스 */}
          <div>
            <label style={labelStyle}>도매처</label>
            <select
              value={filterWholesale}
              onChange={e => setFilterWholesale(e.target.value)}
              style={{ ...inputStyle, width: 150 }}
            >
              <option value="">전체</option>
              {wholesaleOptions.map(w => (
                <option key={w} value={w}>{w}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={labelStyle}>상태</label>
            <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} style={{ ...inputStyle, width: 140 }}>
              <option value="">전체</option>
              <option value="ocr_pending">장끼 확인 중</option>
              <option value="confirming">수량 확인 중</option>
              <option value="inbound_done">입고접수 완료</option>
              <option value="grading">양품화 중</option>
              <option value="repairing">수선 중</option>
              <option value="done">최종완료</option>
              <option value="cancelled">취소</option>
              <option value="etc">기타</option>
            </select>
          </div>
          <div>
            <label style={labelStyle}>기간</label>
            <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
              <input type="date" value={filterDateFrom} onChange={e => setFilterDateFrom(e.target.value)} style={inputStyle} />
              <span style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>~</span>
              <input type="date" value={filterDateTo} onChange={e => setFilterDateTo(e.target.value)} style={inputStyle} />
            </div>
          </div>
          <button onClick={() => load(token)} style={btn('var(--color-brand)')}>조회</button>
          <button
            onClick={() => { setFilterVendor(''); setFilterAlias(''); setFilterWholesale(''); setFilterStatus(''); setFilterDateFrom(''); setFilterDateTo(''); }}
            style={btnOutline}
          >
            초기화
          </button>
        </div>
        {/* 활성 필터 칩 표시 */}
        {(filterVendor || filterAlias || filterWholesale) && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: '0.5rem', paddingTop: '0.5rem', borderTop: '1px solid #f3f4f6' }}>
            <span style={{ fontSize: '0.73rem', color: 'var(--text-secondary)', alignSelf: 'center' }}>필터:</span>
            {filterVendor && (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.75rem', background: '#ede9fe', color: '#7c3aed', borderRadius: 12, padding: '2px 10px', fontWeight: 600 }}>
                🏢 화주사: {filterVendor}
                <button onClick={() => setFilterVendor('')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#7c3aed', fontSize: '0.8rem', padding: 0, lineHeight: 1 }}>×</button>
              </span>
            )}
            {filterAlias && (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.75rem', background: '#dbeafe', color: '#1d4ed8', borderRadius: 12, padding: '2px 10px', fontWeight: 600 }}>
                🏷️ 별칭: {filterAlias}
                <button onClick={() => setFilterAlias('')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#1d4ed8', fontSize: '0.8rem', padding: 0, lineHeight: 1 }}>×</button>
              </span>
            )}
            {filterWholesale && (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.75rem', background: '#fef9c3', color: '#a16207', borderRadius: 12, padding: '2px 10px', fontWeight: 600 }}>
                🏪 도매처: {filterWholesale}
                <button onClick={() => setFilterWholesale('')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#a16207', fontSize: '0.8rem', padding: 0, lineHeight: 1 }}>×</button>
              </span>
            )}
          </div>
        )}
      </Card>

      {/* 결과 수 */}
      <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
        총 {total}건
      </div>

      {/* 목록 */}
      {loading ? (
        <Loading />
      ) : batches.length === 0 ? (
        <Card>
          <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
            <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>📦</div>
            <div style={{ fontSize: '0.9rem', marginBottom: '1rem' }}>입고 데이터가 없습니다.</div>
            <button onClick={() => setShowCreate(true)} style={btn('var(--color-brand)')}>
              첫 입고 등록하기
            </button>
          </div>
        </Card>
      ) : (
        <Card style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={{ ...thStyle, textAlign: 'left' }}>입고일</th>
                  <th style={{ ...thStyle, textAlign: 'left' }}>화주사</th>
                  <th style={{ ...thStyle, textAlign: 'left' }}>도매처</th>
                  <th style={{ ...thStyle, textAlign: 'center' }}>상태</th>
                  <th style={{ ...thStyle, textAlign: 'center' }}>장끼수량</th>
                  <th style={{ ...thStyle, textAlign: 'center' }}>실입고</th>
                  <th style={{ ...thStyle, textAlign: 'center' }}>미입고</th>
                  <th style={{ ...thStyle, textAlign: 'left' }}>등록자</th>
                  <th style={{ ...thStyle, textAlign: 'left' }}>등록일시</th>
                  <th style={thStyle}></th>
                </tr>
              </thead>
              <tbody>
                {batches.map(b => (
                  <tr
                    key={b.id}
                    onClick={() => openDetail(b)}
                    style={{ cursor: 'pointer', transition: 'background 0.1s' }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#f0f4ff')}
                    onMouseLeave={e => (e.currentTarget.style.background = '')}
                  >
                    <td style={{ ...tdStyle, fontWeight: 600 }}>{b.inbound_date}</td>
                    <td style={tdStyle}>{b.vendor}</td>
                    <td style={{ ...tdStyle, color: 'var(--text-secondary)' }}>{b.wholesale || '-'}</td>
                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                      <StatusBadge status={b.status} label={b.status_label} map={STATUS_COLOR} />
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'center', fontWeight: 700, color: '#1d4ed8' }}>{b.total_janggi_qty}</td>
                    <td style={{ ...tdStyle, textAlign: 'center', fontWeight: 700, color: '#15803d' }}>{b.total_actual_qty}</td>
                    <td style={{ ...tdStyle, textAlign: 'center', fontWeight: 700, color: b.total_missing_qty > 0 ? '#dc2626' : 'var(--text-muted)' }}>
                      {b.total_missing_qty > 0 ? b.total_missing_qty : '-'}
                    </td>
                    <td style={{ ...tdStyle, fontSize: '0.78rem', color: 'var(--text-secondary)' }}>{b.created_by || '-'}</td>
                    <td style={{ ...tdStyle, fontSize: '0.78rem', color: 'var(--text-muted)' }}>{fmt(b.created_at)}</td>
                    <td style={{ ...tdStyle, textAlign: 'right' }} onClick={e => e.stopPropagation()}>
                      <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
                        <button
                          onClick={() => { window.location.href = `/inbound/${b.id}/overview`; }}
                          style={{ background: 'none', border: '1px solid #c7d2fe', borderRadius: 4, color: '#4f46e5', fontSize: '0.78rem', cursor: 'pointer', padding: '0.25rem 0.6rem', fontWeight: 600 }}
                          title="통합 처리현황"
                        >
                          통합 현황
                        </button>
                        <button
                          onClick={() => setEditingBatch(b)}
                          style={{ background: 'none', border: '1px solid #fde68a', borderRadius: 4, color: '#d97706', fontSize: '0.78rem', cursor: 'pointer', padding: '0.25rem 0.6rem' }}
                        >
                          수정
                        </button>
                        <button
                          onClick={() => handleDelete(b.id)}
                          style={{ background: 'none', border: '1px solid #fca5a5', borderRadius: 4, color: '#dc2626', fontSize: '0.78rem', cursor: 'pointer', padding: '0.25rem 0.6rem' }}
                        >
                          삭제
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* 모달들 */}
      {showCreate && (
        <CreateBatchModal
          token={token}
          onClose={() => setShowCreate(false)}
          onCreated={batch => { setShowCreate(false); setSelectedBatch(batch); load(token); refreshFilterOptions(token); }}
        />
      )}
      {editingBatch && (
        <EditBatchModal
          batch={editingBatch}
          token={token}
          onClose={() => setEditingBatch(null)}
          onUpdated={() => { load(token); setEditingBatch(null); }}
        />
      )}
      {selectedBatch && (
        <BatchDetailModal
          batch={selectedBatch}
          token={token}
          onClose={() => setSelectedBatch(null)}
          onUpdated={() => load(token)}
        />
      )}
    </div>
  );
}
