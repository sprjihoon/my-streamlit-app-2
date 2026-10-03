'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import { Alert } from '@/components/Alert';
import {
  listInboundBatches,
  createInboundBatch,
  getInboundBatch,
  updateInboundBatch,
  updateInboundItem,
  addInboundItem,
  deleteInboundBatch,
  listInboundVendors,
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
import PageHeader from '@/components/PageHeader';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { EmptyState, OpsModal, StatusBadge } from '@/components/operational';

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
  return <OpsModal title={title} onClose={onClose} wide={wide}>{children}</OpsModal>;
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

  // 바코드 검색 (수정 폼용) — 업체 사전 로드 후 로컬 필터
  const [bcQuery, setBcQuery] = useState(item.matched_barcode || '');
  const [bcAllItems, setBcAllItems] = useState<RepairBarcode[]>([]);  // 업체 전체 바코드
  const [bcOpen, setBcOpen] = useState(false);
  const [bcLoading, setBcLoading] = useState(false);
  const bcRef = useRef<HTMLDivElement>(null);

  // editMode 열릴 때 해당 업체(+ 별칭) 바코드 전체 사전 로드
  useEffect(() => {
    if (!editMode || !batchVendor) return;
    setBcLoading(true);
    // 별칭 그룹 조회 후 해당 업체의 모든 별칭 포함해서 로드
    getVendorAliases(token)
      .then(({ aliases }) => {
        const group = aliases.find(a =>
          a.canonical === batchVendor || a.aliases.includes(batchVendor)
        );
        const vendors = group
          ? [group.canonical, ...group.aliases]
          : [batchVendor];
        return Promise.all(vendors.map(v => getRepairBarcodes({ vendor: v, limit: 500 })));
      })
      .then(results => {
        const seen = new Set<string>();
        setBcAllItems(results.flatMap(r => r.items).filter(b => {
          if (seen.has(b.바코드)) return false;
          seen.add(b.바코드); return true;
        }));
      })
      .catch(() => setBcAllItems([]))
      .finally(() => setBcLoading(false));
  }, [editMode, batchVendor, token]);

  useEffect(() => {
    function h(e: MouseEvent) {
      if (bcRef.current && !bcRef.current.contains(e.target as Node)) setBcOpen(false);
    }
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  // 로컬 필터 (업체 사전 로드된 목록에서 검색)
  const bcFiltered = bcQuery.length > 0
    ? bcAllItems.filter(b => {
        const q = bcQuery.toLowerCase();
        return b.바코드.toLowerCase().includes(q)
          || b.제품명.toLowerCase().includes(q)
          || (b.옵션 || '').toLowerCase().includes(q);
      }).slice(0, 50)
    : bcAllItems.slice(0, 50);

  function handleBcInput(v: string) {
    setBcQuery(v);
    setEditForm(f => ({ ...f, matched_barcode: v }));
    setBcOpen(true);
  }

  function selectBcItem(b: RepairBarcode) {
    setBcQuery(b.바코드);
    setBcOpen(false);
    setEditForm(f => ({
      ...f,
      matched_barcode: b.바코드,
      matched_vendor: b.도매처 || b.업체명 || f.matched_vendor,
      matched_product: b.제품명 || f.matched_product,
      matched_option: b.옵션 || f.matched_option,
      supplier_location: b.도매처주소 || f.supplier_location,
      supplier_contact: b.도매처연락처 || f.supplier_contact,
    }));
  }

  async function save() {
    setSaving(true);
    try {
      await updateInboundItem(token, item.id, { actual_qty: actualQty, missing_qty: missingQty });
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
  const bcDropStyle: React.CSSProperties = {
    position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 700,
    background: '#fff', border: '1px solid #c7d2fe', borderRadius: 6,
    boxShadow: '0 4px 16px rgba(0,0,0,0.12)', maxHeight: 200, overflowY: 'auto', marginTop: 2,
  };

  return (
    <>
      <tr className="tw-bg-white">
        {/* No */}
        <td className="tw-border-b tw-border-solid tw-border-[#f3f4f6] tw-text-[#9ca3af] tw-text-[0.85rem] tw-py-[0.7rem] tw-px-[1rem] tw-text-center tw-align-middle">{item.line_no}</td>
        {/* 날짜 */}
        <td className="tw-border-b tw-border-solid tw-border-[#f3f4f6] tw-text-tillion-muted tw-text-[0.85rem] tw-py-[0.7rem] tw-px-[1rem] tw-align-middle">{batchDate || '-'}</td>
        {/* 업체명 */}
        <td className="tw-border-b tw-border-solid tw-border-[#f3f4f6] tw-text-[0.85rem] tw-font-medium tw-py-[0.7rem] tw-px-[1rem] tw-align-middle">{batchVendor || '-'}</td>
        {/* 도매처 */}
        <td className="tw-border-b tw-border-solid tw-border-[#f3f4f6] tw-text-tillion-muted tw-text-[0.85rem] tw-py-[0.7rem] tw-px-[1rem] tw-align-middle">{batchWholesale || '-'}</td>
        {/* 제품명 */}
        <td style={tdWrap}>
          <div className="tw-font-medium">{item.item_name || '-'}</div>
        </td>
        {/* 옵션 */}
        <td style={tdWrap}>
          <div className="tw-text-tillion-muted tw-text-[0.78rem]">{item.option_text || '-'}</div>
        </td>
        {/* 바코드 */}
        <td className="tw-border-b tw-border-solid tw-border-[#f3f4f6] tw-text-tillion-muted tw-font-mono tw-text-[0.75rem] tw-py-[0.7rem] tw-px-[1rem] tw-align-middle">
          {item.matched_barcode || '-'}
        </td>
        {/* 장끼수량 */}
        <td className="tw-border-b tw-border-solid tw-border-[#f3f4f6] tw-text-[#1d4ed8] tw-text-[0.85rem] tw-font-semibold tw-py-[0.7rem] tw-px-[1rem] tw-text-center tw-align-middle">{item.janggi_qty}</td>
        {/* 실입고 */}
        <td className="tw-border-b tw-border-solid tw-border-[#f3f4f6] tw-text-[0.85rem] tw-py-[0.7rem] tw-px-[1rem] tw-text-center tw-align-middle">
          <input
            type="number" min={0} value={actualQty}
            onChange={e => setActualQty(Number(e.target.value))}
            className="ui-control tw-py-[0.2rem] tw-px-[0.25rem] tw-text-center tw-w-[52px]"
          />
        </td>
        {/* 미입고 */}
        <td className="tw-border-b tw-border-solid tw-border-[#f3f4f6] tw-text-[0.85rem] tw-py-[0.7rem] tw-px-[1rem] tw-text-center tw-align-middle">
          <input
            type="number" min={0} value={missingQty}
            onChange={e => setMissingQty(Number(e.target.value))}
            className="ui-control tw-py-[0.2rem] tw-px-[0.25rem] tw-text-center tw-w-[52px]"
          />
        </td>
        {/* 공급처상품명 */}
        <td style={tdWrap}>
          <div className="tw-text-[#7c3aed] tw-text-[0.78rem] tw-font-semibold">{item.matched_vendor || '-'}</div>
          <div className="tw-text-[0.78rem]">{item.matched_product || '-'}</div>
        </td>
        {/* 공급처옵션 */}
        <td className="tw-border-b tw-border-solid tw-border-[#f3f4f6] tw-text-tillion-muted tw-text-[0.78rem] tw-py-[0.7rem] tw-px-[1rem] tw-align-middle">{item.matched_option || '-'}</td>
        {/* 공급처위치 */}
        <td className="tw-border-b tw-border-solid tw-border-[#f3f4f6] tw-text-[#374151] tw-text-[0.78rem] tw-py-[0.7rem] tw-px-[1rem] tw-align-middle">{item.supplier_location || '-'}</td>
        {/* 공급처연락처 */}
        <td className="tw-border-b tw-border-solid tw-border-[#f3f4f6] tw-text-[#374151] tw-text-[0.78rem] tw-py-[0.7rem] tw-px-[1rem] tw-align-middle">{item.supplier_contact || '-'}</td>
        {/* 작성자 */}
        <td className="tw-border-b tw-border-solid tw-border-[#f3f4f6] tw-text-tillion-muted tw-text-[0.75rem] tw-py-[0.7rem] tw-px-[1rem] tw-align-middle">{batchCreatedBy || '-'}</td>
        {/* 수정시간 */}
        <td className="tw-border-b tw-border-solid tw-border-[#f3f4f6] tw-text-[#9ca3af] tw-text-[0.73rem] tw-py-[0.7rem] tw-px-[1rem] tw-align-middle">
          {item.updated_at ? item.updated_at.slice(0, 16).replace('T', ' ') : '-'}
        </td>
        {/* 사진 */}
        <td className="tw-border-b tw-border-solid tw-border-[#f3f4f6] tw-text-[0.85rem] tw-py-[0.7rem] tw-px-[1rem] tw-text-center tw-align-middle">
          {photoCount > 0
            ? <span className="tw-bg-[#f0fdfa] tw-border tw-border-solid tw-border-[#99f6e4] tw-rounded-[4px] tw-text-[#0f766e] tw-text-[0.78rem] tw-py-[2px] tw-px-[6px]">📷 {photoCount}</span>
            : <span className="tw-text-[#d1d5db] tw-text-[0.75rem]">-</span>
          }
        </td>
        {/* 액션 */}
        <td className="tw-border-b tw-border-solid tw-border-[#f3f4f6] tw-text-[0.85rem] tw-py-[0.7rem] tw-px-[1rem] tw-text-center tw-align-middle">
          <div className="tw-flex tw-gap-[3px] tw-justify-center">
            <button onClick={save} disabled={saving} className="tw-bg-tillion-brand tw-border-0 tw-rounded-[6px] tw-text-white tw-cursor-pointer tw-text-[0.75rem] tw-font-medium tw-py-[0.2rem] tw-px-[0.6rem]">
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
                className="tw-bg-tillion-danger tw-border-0 tw-rounded-[6px] tw-text-white tw-cursor-pointer tw-text-[0.73rem] tw-font-medium tw-py-[0.2rem] tw-px-[0.5rem]"
              >
                🗑
              </button>
            )}
          </div>
        </td>
      </tr>
      {/* 수정 폼 인라인 */}
      {editMode && (
        <tr className="tw-bg-[#f0f4ff]">
          <td colSpan={19} className="tw-border-b tw-border-solid tw-border-[#e0e7ff] tw-py-[0.75rem] tw-px-[1rem]">
            <div className="tw-text-tillion-brand tw-text-[0.82rem] tw-font-bold tw-mb-[8px]">✏️ 품목 정보 수정</div>
            <div className="ops-auto-grid">
              {/* 바코드 검색 */}
              <div ref={bcRef} className="tw-col-span-2 tw-relative">
                <div className="tw-text-[#9ca3af] tw-text-[0.73rem] tw-mb-[3px]">
                  바코드 검색
                  {bcLoading && <span className="tw-text-[#a5b4fc] tw-text-[0.65rem] tw-ml-[6px]">검색 중…</span>}
                </div>
                <input
                  value={bcQuery}
                  onChange={e => handleBcInput(e.target.value)}
                  onFocus={() => bcAllItems.length > 0 && setBcOpen(true)}
                  style={editInput}
                  placeholder="바코드 번호 또는 제품명 입력"
                />
                {bcOpen && bcFiltered.length > 0 && (
                  <div style={bcDropStyle}>
                    {bcFiltered.map(b => (
                      <div
                        key={b.바코드}
                        onMouseDown={() => selectBcItem(b)}
                        className="tw-border-b tw-border-solid tw-border-[#f3f4f6] tw-cursor-pointer tw-text-[0.78rem] tw-py-[6px] tw-px-[10px]"
                        onMouseEnter={e => (e.currentTarget.style.background = '#eef2ff')}
                        onMouseLeave={e => (e.currentTarget.style.background = '')}
                      >
                        <span className="tw-text-tillion-brand tw-font-semibold">{b.바코드}</span>
                        <span className="tw-text-[#374151] tw-ml-[6px]">{b.제품명}</span>
                        {b.옵션 && <span className="tw-text-tillion-muted tw-ml-[4px]">/ {b.옵션}</span>}
                        {b.도매처 && <span className="tw-text-[#9ca3af] tw-text-[0.72rem] tw-ml-[6px]">[{b.도매처}]</span>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div>
                <div className="tw-text-[#9ca3af] tw-text-[0.73rem] tw-mb-[3px]">공급처(업체명)</div>
                <input value={editForm.matched_vendor} onChange={e => setEditForm(f => ({ ...f, matched_vendor: e.target.value }))} style={editInput} placeholder="공급처" />
              </div>
              <div>
                <div className="tw-text-[#9ca3af] tw-text-[0.73rem] tw-mb-[3px]">공급처 상품명</div>
                <input value={editForm.matched_product} onChange={e => setEditForm(f => ({ ...f, matched_product: e.target.value }))} style={editInput} placeholder="공급처 상품명" />
              </div>
              <div>
                <div className="tw-text-[#9ca3af] tw-text-[0.73rem] tw-mb-[3px]">공급처 옵션</div>
                <input value={editForm.matched_option} onChange={e => setEditForm(f => ({ ...f, matched_option: e.target.value }))} style={editInput} placeholder="공급처 옵션" />
              </div>
              <div>
                <div className="tw-text-[#9ca3af] tw-text-[0.73rem] tw-mb-[3px]">공급처 위치</div>
                <input value={editForm.supplier_location} onChange={e => setEditForm(f => ({ ...f, supplier_location: e.target.value }))} style={editInput} placeholder="예) A동 3층" />
              </div>
              <div>
                <div className="tw-text-[#9ca3af] tw-text-[0.73rem] tw-mb-[3px]">공급처 연락처</div>
                <input value={editForm.supplier_contact} onChange={e => setEditForm(f => ({ ...f, supplier_contact: e.target.value }))} style={editInput} placeholder="010-0000-0000" />
              </div>
              <div>
                <div className="tw-text-[#9ca3af] tw-text-[0.73rem] tw-mb-[3px]">메모</div>
                <input value={editForm.memo} onChange={e => setEditForm(f => ({ ...f, memo: e.target.value }))} style={editInput} placeholder="메모" />
              </div>
            </div>
            <div className="tw-flex tw-gap-[8px]">
              <button onClick={saveEdit} disabled={editSaving} style={{ ...btn('#4361ee'), opacity: editSaving ? 0.5 : 1 }}>
                {editSaving ? '저장 중…' : '수정 저장'}
              </button>
              <button onClick={() => setEditMode(false)} className="btn btn-secondary">취소</button>
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
    setBarcodeOpen(false);
    setForm(f => ({ ...f, item_name: f.item_name || b.제품명, option_text: f.option_text || (b.옵션 || '') }));
  }

  const fvq = vendorQuery.toLowerCase();
  const fVendors = vendorList.filter(v => v.name.toLowerCase().includes(fvq) || v.aliases.some(a => a.toLowerCase().includes(fvq)));
  const fAliases = aliasList.filter(a => a.canonical.toLowerCase().includes(fvq) || a.aliases.some(al => al.toLowerCase().includes(fvq)));
  const fbq = barcodeQuery.toLowerCase();
  const fBarcodes = barcodeResults.filter(b =>
    b.바코드.toLowerCase().includes(fbq) || b.제품명.toLowerCase().includes(fbq) ||
    (b.옵션 || '').toLowerCase().includes(fbq) || b.업체명.toLowerCase().includes(fbq)
  );

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
        className="ops-inline-add"
      >
        ➕ 품목 직접 추가
      </button>
    );
  }

  return (
    <div className="tw-bg-[#f8faff] tw-border tw-border-solid tw-border-[#c7d2fe] tw-rounded-[8px] tw-mb-[1rem] tw-p-[1rem]">
      <div className="tw-items-center tw-flex tw-justify-between tw-mb-[0.75rem]">
        <span className="tw-text-tillion-brand tw-text-[0.9rem] tw-font-bold">➕ 품목 직접 추가</span>
        <button onClick={() => { setOpen(false); resetForm(); }} className="tw-bg-transparent tw-border-0 tw-text-tillion-muted tw-cursor-pointer tw-text-[1.1rem]">×</button>
      </div>

      <div className="tw-grid tw-gap-[0.6rem] tw-grid-cols-2 tw-mb-[0.6rem]">
        {/* 업체 선택 */}
        <div ref={vendorRef} className="tw-col-span-full tw-relative">
          <label className="ops-label">업체 (등록업체·별칭 검색)</label>
          <input
            value={vendorQuery}
            onChange={e => { setVendorQuery(e.target.value); setVendorOpen(true); if (!e.target.value) { setSelectedVendors([]); setVendorDisplay(''); } }}
            onFocus={() => setVendorOpen(true)}
            placeholder="업체명 또는 별칭 검색…"
            className="ui-control"
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
                      {v.aliases.length > 0 && <span className="tw-text-[#9ca3af] tw-text-[11px] tw-ml-[6px]">({v.aliases.join(', ')})</span>}
                    </div>
                  ))}
                </>
              )}
              {fAliases.length > 0 && (
                <>
                  <div style={grpLbl}>🏷️ 화주사 별칭</div>
                  {fAliases.map(a => (
                    <div key={a.canonical} onMouseDown={() => selectVendor(a.canonical, a.aliases)}
                      className="tw-cursor-pointer tw-text-[13px] tw-py-[7px] tw-px-[12px]">
                      <span className="tw-text-[#1d4ed8] tw-font-semibold">{a.canonical}</span>
                      {a.aliases.length > 0 && <span className="tw-text-[#9ca3af] tw-text-[11px] tw-ml-[6px]">→ {a.aliases.join(', ')}</span>}
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>

        {/* 바코드 검색 */}
        <div ref={barcodeRef} className="tw-col-span-full tw-relative">
          <label className="ops-label">바코드 검색 {barcodeLoading ? '(불러오는 중…)' : selectedVendors.length > 0 ? `(${barcodeResults.length}개)` : ''}</label>
          {selectedVendors.length === 0 ? (
            <div className="tw-text-[#9ca3af] tw-text-[0.8rem] tw-py-[0.4rem] tw-px-0">↑ 업체를 먼저 선택하면 해당 업체 바코드를 검색할 수 있습니다.</div>
          ) : barcodeLoading ? (
            <div className="tw-text-[#9ca3af] tw-text-[0.8rem]">바코드 목록 불러오는 중…</div>
          ) : barcodeResults.length === 0 ? (
            <div className="tw-bg-[#fef2f2] tw-border tw-border-solid tw-border-[#fecaca] tw-rounded-[6px] tw-text-[0.82rem] tw-py-[0.6rem] tw-px-[0.8rem]">
              <span className="tw-text-[#b42318]">"{vendorDisplay}" 업체의 등록 바코드가 없습니다. </span>
              <a href="/journal-settings" target="_blank" className="tw-text-tillion-brand tw-font-semibold">신규 바코드 등록 →</a>
              <div className="tw-text-[#9ca3af] tw-text-[0.75rem] tw-mt-[3px]">아래에 품명을 직접 입력하거나, 바코드 등록 후 다시 시도하세요.</div>
            </div>
          ) : (
            <>
              {selectedBarcode ? (
                <div className="tw-items-center tw-flex tw-gap-[6px]">
                  <div className="tw-bg-[#ede9fe] tw-rounded-[6px] tw-text-[#7c3aed] tw-flex-1 tw-text-[0.82rem] tw-font-medium tw-py-[0.4rem] tw-px-[0.65rem]">
                    ✅ {selectedBarcode.바코드} — {selectedBarcode.업체명} / {selectedBarcode.제품명}{selectedBarcode.옵션 ? ' / ' + selectedBarcode.옵션 : ''}
                  </div>
                  <button onClick={() => { setSelectedBarcode(null); setBarcodeQuery(''); }} className="btn btn-secondary tw-text-[0.75rem] tw-py-[0.3rem] tw-px-[0.6rem]">변경</button>
                </div>
              ) : (
                <>
                  <input
                    value={barcodeQuery}
                    onChange={e => { setBarcodeQuery(e.target.value); setBarcodeOpen(true); }}
                    onFocus={() => setBarcodeOpen(true)}
                    placeholder={`바코드·제품명 검색 (${barcodeResults.length}개 중)`}
                    className="ui-control"
                  />
                  {barcodeOpen && fBarcodes.length > 0 && (
                    <div style={dropBase}>
                      {fBarcodes.slice(0, 50).map(b => (
                        <div key={b.바코드} onMouseDown={() => selectBarcode(b)}
                          className="tw-border-b tw-border-solid tw-border-[#f3f4f6] tw-cursor-pointer tw-py-[7px] tw-px-[12px]">
                          <div className="tw-items-start tw-flex tw-justify-between">
                            <div>
                              <span className="tw-text-[13px] tw-font-medium">{b.제품명}</span>
                              {b.옵션 && <span className="tw-text-tillion-muted tw-text-[12px]"> / {b.옵션}</span>}
                              <div className="tw-text-[#9ca3af] tw-font-mono tw-text-[11px]">{b.바코드}</div>
                            </div>
                            <span className="tw-text-[#7c3aed] tw-shrink-0 tw-text-[11px] tw-ml-[8px]">{b.업체명}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>

        {/* 품명 */}
        <div className="tw-col-span-full">
          <label className="ops-label">품명 *</label>
          <input value={form.item_name} onChange={e => setForm(f => ({ ...f, item_name: e.target.value }))} placeholder="예) 타원 백팩" className="ui-control" />
        </div>

        {/* 옵션 */}
        <div>
          <label className="ops-label">옵션</label>
          <input value={form.option_text} onChange={e => setForm(f => ({ ...f, option_text: e.target.value }))} placeholder="블랙, L" className="ui-control" />
        </div>

        {/* 장끼 수량 */}
        <div>
          <label className="ops-label">장끼 수량 *</label>
          <input type="number" min={1} value={form.janggi_qty} onChange={e => setForm(f => ({ ...f, janggi_qty: Number(e.target.value) }))}
            style={{ ...inp, textAlign: 'center', fontWeight: 700, fontSize: '1rem' }} />
        </div>

        {/* 단가 */}
        <div className="tw-col-span-full">
          <label className="ops-label">단가 (선택)</label>
          <input type="number" min={0} value={form.unit_price} onChange={e => setForm(f => ({ ...f, unit_price: e.target.value }))}
            placeholder="0" style={{ ...inp, maxWidth: 160 }} />
        </div>
      </div>

      <div className="tw-flex tw-gap-[8px]">
        <button onClick={() => { setOpen(false); resetForm(); }} className="btn btn-secondary">취소</button>
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
    <div ref={wrapRef} className="tw-relative tw-w-full">
      <div className="tw-flex tw-gap-[4px]">
        <input
          value={query}
          onChange={e => handleInput(e.target.value)}
          onFocus={() => setOpen(true)}
          placeholder="업체명 검색 또는 직접 입력"
          className="ui-control tw-flex-1"
          autoComplete="off"
        />
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          className="btn btn-secondary tw-text-[12px] tw-min-w-[32px] tw-py-0 tw-px-[10px]"
          title="목록 열기"
        >▾</button>
      </div>

      {/* 선택된 등록업체 뱃지 */}
      {canonical && (
        <div className="tw-items-center tw-flex tw-gap-[6px] tw-mt-[4px]">
          <span className="tw-bg-[#ede9fe] tw-rounded-[4px] tw-text-tillion-brand tw-text-[11px] tw-py-[2px] tw-px-[7px]">
            📦 등록업체: {canonical}
          </span>
          <button
            type="button"
            className="tw-bg-transparent tw-border-0 tw-text-tillion-muted tw-cursor-pointer tw-text-[11px] tw-p-0"
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
                    <span className="tw-font-medium">{v.name}</span>
                    {v.aliases.length > 0 && (
                      <span className="tw-text-[#9ca3af] tw-text-[11px] tw-ml-[6px]">
                        ({v.aliases.join(', ')})
                      </span>
                    )}
                  </div>
                  {v.name === canonical && <span className="tw-text-tillion-brand tw-text-[12px]">✓</span>}
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
        <div className="tw-text-[14px] tw-font-bold tw-mb-[0.75rem]">
          ✎ &quot;{vendor.name}&quot; 별칭 관리
        </div>
        <div className="tw-text-tillion-muted tw-text-[12px] tw-mb-[8px]">
          쉼표로 구분. OCR이 별칭으로 읽어도 이 업체 바코드 목록에서 매칭합니다.
        </div>
        <textarea
          value={aliases}
          onChange={e => setAliases(e.target.value)}
          placeholder="예: ABC코리아, 에이비씨, ABC"
          rows={3}
          className="ui-control tw-resize-y tw-w-full"
        />
        <div className="tw-flex tw-gap-[8px] tw-justify-end tw-mt-[12px]">
          <button onClick={onClose} className="btn btn-secondary">취소</button>
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
          <label className="ops-label">화주사 *</label>
          <VendorCombobox
            token={token}
            value={vendor}
            canonical={vendorCanonical}
            onChange={(display, can) => { setVendor(display); setVendorCanonical(can); }}
          />
        </div>
        <div style={fRow}>
          <label className="ops-label">입고일 *</label>
          <input type="date" value={inboundDate} onChange={e => setInboundDate(e.target.value)} className="ui-control" />
        </div>
        <div style={fRow}>
          <label className="ops-label">메모 (선택)</label>
          <input
            value={memo} onChange={e => setMemo(e.target.value)}
            placeholder="메모"
            className="ui-control tw-w-full"
          />
        </div>
        <div className="tw-flex tw-gap-[0.5rem] tw-justify-end tw-pt-[0.5rem]">
          <button onClick={onClose} className="btn btn-secondary">취소</button>
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
          <label className="ops-label">화주사</label>
          <input
            value={vendor} onChange={e => setVendor(e.target.value)}
            className="ui-control tw-w-full"
          />
        </div>
        <div style={fRow}>
          <label className="ops-label">입고일</label>
          <input type="date" value={inboundDate} onChange={e => setInboundDate(e.target.value)} className="ui-control" />
        </div>
        <div style={fRow}>
          <label className="ops-label">도매처</label>
          <input
            value={wholesale} onChange={e => setWholesale(e.target.value)}
            placeholder="도매처 이름"
            className="ui-control tw-w-full"
          />
        </div>
        <div style={fRow}>
          <label className="ops-label">메모</label>
          <input
            value={memo} onChange={e => setMemo(e.target.value)}
            placeholder="메모"
            className="ui-control tw-w-full"
          />
        </div>
        <div className="tw-flex tw-gap-[0.5rem] tw-justify-end tw-pt-[0.5rem]">
          <button onClick={onClose} className="btn btn-secondary">취소</button>
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
  const router = useRouter();
  const [token, setToken] = useState('');
  const [batches, setBatches] = useState<InboundBatch[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showCreate, setShowCreate] = useState(false);
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

  function openDetail(batch: InboundBatch) {
    router.push('/inbound-overview/detail?vendor=' + encodeURIComponent(batch.vendor) + '&date=' + batch.inbound_date);
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

  return (
    <div>
      <PageHeader
        title="입고일지"
        subtitle="장끼 OCR → 상품 매칭 → 실수량 확인 → 양품화 → 마감"
        actions={<Button type="button" onClick={() => setShowCreate(true)}>입고 등록</Button>}
      />

      {message && <Alert type={message.type} message={message.text} onClose={() => setMessage(null)} />}

      <div className="ops-filter-panel">
        <div className="ops-filter">
          <Field label="화주사">
            <Select
              value={filterVendor}
              onChange={e => { setFilterVendor(e.target.value); setFilterAlias(''); }}
            >
              <option value="">전체</option>
              {vendorOptions.map(v => (
                <option key={v} value={v}>{v}</option>
              ))}
            </Select>
          </Field>
          <Field label="별칭" hint="일지설정 기준">
            <Select
              value={filterAlias}
              onChange={e => { setFilterAlias(e.target.value); setFilterVendor(''); }}
            >
              <option value="">전체</option>
              {aliasGroups.map(g =>
                g.aliases.map(alias => (
                  <option key={`${g.canonical}__${alias}`} value={alias}>
                    {alias} ({g.canonical})
                  </option>
                ))
              )}
            </Select>
          </Field>
          <Field label="도매처">
            <Select value={filterWholesale} onChange={e => setFilterWholesale(e.target.value)}>
              <option value="">전체</option>
              {wholesaleOptions.map(w => (
                <option key={w} value={w}>{w}</option>
              ))}
            </Select>
          </Field>
          <Field label="상태">
            <Select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
              <option value="">전체</option>
              <option value="ocr_pending">장끼 확인 중</option>
              <option value="confirming">수량 확인 중</option>
              <option value="inbound_done">입고접수 완료</option>
              <option value="grading">양품화 중</option>
              <option value="repairing">수선 중</option>
              <option value="done">최종완료</option>
              <option value="cancelled">취소</option>
              <option value="etc">기타</option>
            </Select>
          </Field>
          <Field label="기간" className="is-period">
            <div className="ops-period">
              <Input type="date" value={filterDateFrom} onChange={e => setFilterDateFrom(e.target.value)} />
              <span>~</span>
              <Input type="date" value={filterDateTo} onChange={e => setFilterDateTo(e.target.value)} />
            </div>
          </Field>
          <div className="ops-filter-actions">
            <Button type="button" onClick={() => load(token)}>조회</Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => { setFilterVendor(''); setFilterAlias(''); setFilterWholesale(''); setFilterStatus(''); setFilterDateFrom(''); setFilterDateTo(''); }}
            >
              초기화
            </Button>
          </div>
        </div>
        {(filterVendor || filterAlias || filterWholesale) && (
          <div className="ops-chips">
            {filterVendor && (
              <span className="ops-chip">
                화주사: {filterVendor}
                <button type="button" onClick={() => setFilterVendor('')} aria-label="화주사 필터 제거">×</button>
              </span>
            )}
            {filterAlias && (
              <span className="ops-chip">
                별칭: {filterAlias}
                <button type="button" onClick={() => setFilterAlias('')} aria-label="별칭 필터 제거">×</button>
              </span>
            )}
            {filterWholesale && (
              <span className="ops-chip">
                도매처: {filterWholesale}
                <button type="button" onClick={() => setFilterWholesale('')} aria-label="도매처 필터 제거">×</button>
              </span>
            )}
          </div>
        )}
      </div>

      <p className="ops-result-count">총 {total}건</p>

      {loading ? (
        <Loading />
      ) : batches.length === 0 ? (
        <Card>
          <EmptyState
            title="입고 데이터가 없습니다."
            action={<Button type="button" onClick={() => setShowCreate(true)}>첫 입고 등록하기</Button>}
          />
        </Card>
      ) : (
        <Card className="!tw-p-0 tw-overflow-hidden">
          <div className="ops-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>입고일</th>
                  <th>화주사</th>
                  <th>도매처</th>
                  <th className="ops-center">상태</th>
                  <th className="ops-center">장끼수량</th>
                  <th className="ops-center">실입고</th>
                  <th className="ops-center">미입고</th>
                  <th>등록자</th>
                  <th>등록일시</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {batches.map(b => (
                  <tr key={b.id} className="ops-click-row" onClick={() => openDetail(b)}>
                    <td className="ops-strong">{b.inbound_date}</td>
                    <td>{b.vendor}</td>
                    <td className="ops-subtle">{b.wholesale || '-'}</td>
                    <td className="ops-center"><StatusBadge status={b.status} label={b.status_label} /></td>
                    <td className="ops-num-info">{b.total_janggi_qty}</td>
                    <td className="ops-num-ok">{b.total_actual_qty}</td>
                    <td className={b.total_missing_qty > 0 ? 'ops-num-bad' : 'ops-num-muted'}>
                      {b.total_missing_qty > 0 ? b.total_missing_qty : '-'}
                    </td>
                    <td className="ops-subtle">{b.created_by || '-'}</td>
                    <td className="ops-subtle">{fmt(b.created_at)}</td>
                    <td className="ops-right" onClick={e => e.stopPropagation()}>
                      <div className="ops-mini-row">
                        <button type="button" className="ops-mini" onClick={() => { window.location.href = `/inbound/${b.id}/overview`; }} title="통합 처리현황">통합 현황</button>
                        <button type="button" className="ops-mini is-warn" onClick={() => setEditingBatch(b)}>수정</button>
                        <button type="button" className="ops-mini is-danger" onClick={() => handleDelete(b.id)}>삭제</button>
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
          onCreated={batch => { setShowCreate(false); openDetail(batch); load(token); refreshFilterOptions(token); }}
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
    </div>
  );
}
