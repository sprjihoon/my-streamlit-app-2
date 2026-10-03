'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { useParams } from 'next/navigation';
import {
  getInboundBatch,
  addInboundItem,
  updateInboundItem,
  deleteInboundItem,
  closeInboundBatch,
  gradeCompleteInboundBatch,
  runInboundOcr,
  listInboundVendors,
  listInboundInboxPhotos,
  linkInboxPhotoToItem,
  unlinkInboxPhotoFromItem,
  getRepairBarcodes,
  getVendorAliases,
  ApiError,
  InboundBatch,
  InboundItem,
  InboundInboxPhoto,
  InboundRegisteredVendor,
  VendorAlias,
  RepairBarcode,
} from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { EmptyState, StatusBadge } from '@/components/operational';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ─── 토큰 ─────────────────────────────
function getToken() {
  if (typeof window === 'undefined') return '';
  return localStorage.getItem('token') || '';
}
function inboundAuthHeaders(token: string) {
  return { Authorization: `Bearer ${token}` };
}

// ─── 색상 시스템 ──────────────────────
const C = {
  brand:        '#4f46e5',
  brandLight:   '#eef2ff',
  brandBorder:  '#c7d2fe',
  success:      '#16a34a',
  successLight: '#dcfce7',
  successBorder:'#86efac',
  danger:       '#dc2626',
  dangerLight:  '#fef2f2',
  dangerBorder: '#fecaca',
  warning:      '#d97706',
  warningLight: '#fef9c3',
  warningBorder:'#fde68a',
  purple:       '#7c3aed',
  purpleLight:  '#ede9fe',
  purpleBorder: '#c4b5fd',
  text:         '#111827',
  textSub:      '#374151',
  textMuted:    '#6b7280',
  textFaint:    '#9ca3af',
  bg:           '#f5f6fa',
  card:         '#ffffff',
  border:       '#e5e7eb',
  borderLight:  '#f3f4f6',
};

// ─── 배치 상태 ────────────────────────
// ─── 공통 스타일 오브젝트 ──────────────
const cardStyle: React.CSSProperties = {
  background: C.card,
  borderRadius: 16,
  marginBottom: 12,
  overflow: 'hidden',
  boxShadow: '0 1px 3px rgba(0,0,0,0.07), 0 4px 12px rgba(0,0,0,0.04)',
};

const inputBase: React.CSSProperties = {
  width: '100%', boxSizing: 'border-box', outline: 'none',
  fontSize: 14, padding: '9px 11px', borderRadius: 8,
  border: `1px solid ${C.border}`,
};

// ─── 섹션 토글 버튼 ──────────────────
function SectionToggle({ open, label, badge, onToggle }: {
  open: boolean; label: string; badge?: React.ReactNode; onToggle: () => void;
}) {
  return (
    <button onClick={onToggle} className="ops-toggle">
      <span className={open ? 'ops-toggle-label is-open' : 'ops-toggle-label'}>{label}</span>
      <span className="ops-toggle-side">
        {badge}
        <span className="ops-toggle-chevron">{open ? '▲' : '▼'}</span>
      </span>
    </button>
  );
}

// ══════════════════════════════════════
// 바코드 드롭다운 아이템 (공통)
// ══════════════════════════════════════
function BarcodeItem({ b }: { b: RepairBarcode }) {
  return (
    <>
      <div className="tw-text-tillion-text tw-text-[13px] tw-font-semibold">
        {b.제품명}{b.옵션 ? ` / ${b.옵션}` : ''}
      </div>
      {b.상품명 && b.상품명 !== b.제품명 && (
        <div className="tw-text-tillion-muted tw-text-[11px] tw-mt-[1px]">
          {b.상품명}
        </div>
      )}
      <div className="tw-text-[#9ca3af] tw-flex tw-font-mono tw-text-[11px] tw-gap-[8px] tw-mt-[2px]">
        <span>{b.바코드}</span>
        {b.도매처 && <span className="tw-text-[#6d28d9] tw-font-[inherit]">{b.도매처}</span>}
        {b.업체명 && <span className="tw-text-[#9ca3af] tw-font-[inherit]">[{b.업체명}]</span>}
      </div>
    </>
  );
}

// ══════════════════════════════════════
// 품목 카드
// ══════════════════════════════════════
function ItemCard({ item, token, workerName, isAdmin, batchVendor, inboxPhotos, onUpdated, onDelete }: {
  item: InboundItem;
  token: string;
  workerName: string;
  isAdmin: boolean;
  batchVendor: string;
  inboxPhotos: InboundInboxPhoto[];  // 배치 전체 inbox 사진 목록
  onUpdated: () => void;
  onDelete?: () => void;
}) {
  const [actualQty,  setActualQty]  = useState(item.actual_qty);
  const [missingQty, setMissingQty] = useState(item.missing_qty);
  const [saving,     setSaving]     = useState(false);
  const [saved,      setSaved]      = useState(false);
  const [uploading,  setUploading]  = useState(false);
  const [photos,     setPhotos]     = useState(item.photos || []);

  // ── 섹션 열림 상태 ──
  const [showMatch,  setShowMatch]  = useState(false);
  const [showPhoto,  setShowPhoto]  = useState(false);
  const [editMode,   setEditMode]   = useState(false);

  // ── 바코드 매칭 상태 ──
  const [editItemName,  setEditItemName]  = useState(item.item_name || '');
  const [editWholesale, setEditWholesale] = useState(item.item_wholesale || batchVendor || '');
  const [nameSaving,  setNameSaving]  = useState(false);
  const [nameSaved,   setNameSaved]   = useState(false);
  const [barcodeQuery,   setBarcodeQuery]   = useState('');
  const [barcodeResults, setBarcodeResults] = useState<RepairBarcode[]>([]);
  const [barcodeLoading, setBarcodeLoading] = useState(false);
  const [matchSaving,  setMatchSaving]  = useState(false);
  const [matchSaved,   setMatchSaved]   = useState(false);
  const [autoMatched,  setAutoMatched]  = useState<RepairBarcode | null>(null);
  const barcodeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── 수정 폼 상태 (관리자) ──
  const [editForm, setEditForm] = useState({
    item_name:        item.item_name        || '',
    option_text:      item.option_text      || '',
    supplier_location:item.supplier_location|| '',
    supplier_contact: item.supplier_contact || '',
    memo:             item.memo             || '',
  });
  const [editSaving, setEditSaving] = useState(false);

  // ── 수정 폼 바코드 검색 ──
  const [editBarcodeQuery,   setEditBarcodeQuery]   = useState('');
  const [editBarcodeResults, setEditBarcodeResults] = useState<RepairBarcode[]>([]);
  const [editBarcodeLoading, setEditBarcodeLoading] = useState(false);
  const [editBarcodeOpen,    setEditBarcodeOpen]    = useState(false);
  const [editSelectedBarcode, setEditSelectedBarcode] = useState<RepairBarcode | null>(null);
  const editBarcodeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const editBarcodeRef = useRef<HTMLDivElement>(null);

  // ── 업체 alias 사전 해석 (편집 바코드 검색 필터용) ──
  const [resolvedVendors, setResolvedVendors] = useState<string[]>([]);
  useEffect(() => {
    if (!batchVendor || !token) return;
    Promise.all([listInboundVendors(token), getVendorAliases(token)])
      .then(([v, a]) => {
        const matched = v.registered.find((r: InboundRegisteredVendor) => r.name === batchVendor || r.aliases.includes(batchVendor));
        const aliasM  = a.aliases.find((al: VendorAlias) => al.canonical === batchVendor);
        if (matched) setResolvedVendors([matched.name]);
        else if (aliasM) setResolvedVendors(aliasM.aliases.length > 0 ? aliasM.aliases : [aliasM.canonical]);
        else setResolvedVendors([batchVendor]);
      }).catch(() => setResolvedVendors([batchVendor]));
  }, [token, batchVendor]);

  // 수정 폼 열릴 때 바코드 검색 초기화
  function openEditMode() {
    setEditForm({
      item_name:        item.item_name        || '',
      option_text:      item.option_text      || '',
      supplier_location:item.supplier_location|| '',
      supplier_contact: item.supplier_contact || '',
      memo:             item.memo             || '',
    });
    setEditBarcodeQuery(''); setEditBarcodeResults([]);
    setEditSelectedBarcode(null); setEditBarcodeOpen(false);
    setEditMode(true);
  }

  // ── 핸들러 (로직 동일) ──
  async function handleSave() {
    setSaving(true); setSaved(false);
    try {
      await updateInboundItem(token, item.id, {
        actual_qty: actualQty, missing_qty: missingQty,
        ...(workerName ? { confirmed_by: workerName } : {}),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
      onUpdated();
    } catch { alert('저장 실패'); }
    finally { setSaving(false); }
  }

  async function handleEditSave() {
    setEditSaving(true);
    try {
      await updateInboundItem(token, item.id, {
        item_name:         editForm.item_name         || undefined,
        option_text:       editForm.option_text       || undefined,
        supplier_location: editForm.supplier_location || undefined,
        supplier_contact:  editForm.supplier_contact  || undefined,
        memo:              editForm.memo              || undefined,
        ...(editSelectedBarcode ? {
          matched_barcode: editSelectedBarcode.바코드,
          matched_vendor:  editSelectedBarcode.업체명,
          // OCR/입력된 상품명을 바코드 마스터에 반영; 없으면 바코드 DB 이름 폴백
          matched_product: (editForm.item_name || '').trim() || editSelectedBarcode.제품명,
          matched_option:  editSelectedBarcode.옵션 || undefined,
        } : {}),
      });
      setEditMode(false); onUpdated();
    } catch { alert('수정 저장 실패'); }
    finally { setEditSaving(false); }
  }

  function handleEditBarcodeInput(val: string) {
    setEditBarcodeQuery(val); setEditSelectedBarcode(null); setEditBarcodeOpen(true);
    if (editBarcodeTimerRef.current) clearTimeout(editBarcodeTimerRef.current);
    if (!val.trim()) { setEditBarcodeResults([]); return; }
    editBarcodeTimerRef.current = setTimeout(async () => {
      setEditBarcodeLoading(true);
      try {
        // resolvedVendors 가 있으면 업체별 필터 검색, 없으면 전체 검색
        const vendorKeys = resolvedVendors.length > 0 ? resolvedVendors : [];
        if (vendorKeys.length === 0) {
          const res = await getRepairBarcodes({ q: val.trim(), limit: 40 });
          setEditBarcodeResults(res.items);
        } else {
          const results = await Promise.all(
            vendorKeys.map(v => getRepairBarcodes({ q: val.trim(), vendor: v, limit: 40 }))
          );
          const seen = new Set<string>();
          const merged = results.flatMap(r => r.items).filter(b => {
            if (seen.has(b.바코드)) return false;
            seen.add(b.바코드); return true;
          });
          setEditBarcodeResults(merged.slice(0, 40));
        }
      } catch { setEditBarcodeResults([]); }
      finally { setEditBarcodeLoading(false); }
    }, 350);
  }

  function selectEditBarcode(b: RepairBarcode) {
    setEditSelectedBarcode(b);
    setEditBarcodeQuery(`${b.바코드} — ${b.제품명}${b.옵션 ? ' / ' + b.옵션 : ''}`);
    setEditBarcodeOpen(false); setEditBarcodeResults([]);
    setEditForm(f => ({
      ...f,
      item_name:   f.item_name   || b.제품명,
      option_text: f.option_text || (b.옵션 || ''),
    }));
  }

  async function saveItemFields() {
    setNameSaving(true);
    try {
      await updateInboundItem(token, item.id, {
        item_name: editItemName.trim() || undefined,
        item_wholesale: editWholesale.trim() || undefined,
        ...(workerName ? { confirmed_by: workerName } : {}),
      });
      setNameSaved(true); setTimeout(() => setNameSaved(false), 2000);
      onUpdated();
    } catch { alert('저장 실패'); }
    finally { setNameSaving(false); }
  }

  async function tryAutoMatch(itemName: string, wholesale: string) {
    if (!itemName.trim()) return;
    setBarcodeLoading(true); setAutoMatched(null);
    try {
      const res = await getRepairBarcodes({ q: itemName.trim(), vendor: batchVendor || undefined, limit: 50 });
      const candidates = res.items;
      if (!candidates.length) { setBarcodeResults([]); return; }
      const ws  = wholesale.trim().toLowerCase();
      const nm  = itemName.trim().toLowerCase();
      const opt = (item.option_text || '').trim().toLowerCase();

      const exact = candidates.filter(b =>
        b.제품명.toLowerCase() === nm &&
        (ws ? (b.도매처 || '').toLowerCase() === ws : true) &&
        opt && b.옵션 && b.옵션.toLowerCase() === opt
      );
      if (exact.length === 1) { setAutoMatched(exact[0]); setBarcodeResults([]); return; }

      const byName = candidates.filter(b =>
        b.제품명.toLowerCase() === nm &&
        (ws ? (b.도매처 || '').toLowerCase() === ws : true)
      );
      if (byName.length === 1) { setAutoMatched(byName[0]); setBarcodeResults([]); return; }
      if (byName.length > 1)   { setBarcodeResults(byName); return; }
      setBarcodeResults(candidates.slice(0, 20));
    } catch { setBarcodeResults([]); }
    finally { setBarcodeLoading(false); }
  }

  function handleBarcodeInput(val: string) {
    setBarcodeQuery(val); setAutoMatched(null);
    if (barcodeTimerRef.current) clearTimeout(barcodeTimerRef.current);
    if (!val.trim()) { setBarcodeResults([]); return; }
    barcodeTimerRef.current = setTimeout(async () => {
      setBarcodeLoading(true);
      try {
        // vendor 필터 적용 — API가 inbound_vendor_aliases 별칭을 자동 해석하므로 안전
        const res = await getRepairBarcodes({ q: val.trim(), vendor: batchVendor || undefined, limit: 40 });
        setBarcodeResults(res.items);
      } catch { setBarcodeResults([]); }
      finally { setBarcodeLoading(false); }
    }, 350);
  }

  async function handleSelectBarcode(b: RepairBarcode) {
    setMatchSaving(true);
    try {
      // OCR로 판독된 상품명(item_name)을 matched_product로 사용 → 바코드 마스터에 반영
      // item_name이 없을 경우에만 바코드 DB의 제품명을 폴백으로 사용
      const productName = (item.item_name || '').trim() || b.제품명;
      await updateInboundItem(token, item.id, {
        matched_barcode: b.바코드, matched_vendor: b.업체명,
        matched_product: productName, matched_option: b.옵션 || undefined,
        ...(workerName ? { confirmed_by: workerName } : {}),
      });
      setMatchSaved(true); setTimeout(() => setMatchSaved(false), 2500);
      setBarcodeQuery(''); setBarcodeResults([]); setAutoMatched(null);
      onUpdated();
    } catch { alert('매칭 저장 실패'); }
    finally { setMatchSaving(false); }
  }

  async function handlePhotoUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch(`${API_BASE}/inbound/items/${item.id}/photos`, {
        method: 'POST', headers: inboundAuthHeaders(token), body: form,
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setPhotos(prev => [...prev, data]);
    } catch (err) {
      alert('사진 업로드 실패: ' + (err instanceof Error ? err.message : String(err)));
    } finally { setUploading(false); e.target.value = ''; }
  }

  async function handlePhotoDelete(photoId: string) {
    if (!confirm('사진을 삭제하시겠습니까?')) return;
    try {
      await fetch(`${API_BASE}/inbound/items/${item.id}/photos/${photoId}`, {
        method: 'DELETE', headers: inboundAuthHeaders(token),
      });
      setPhotos(prev => prev.filter(p => p.id !== photoId));
    } catch { alert('삭제 실패'); }
  }

  const isMatched = !!item.matched_product;

  // ── photo_decision 상태 ──
  const [photoDecision, setPhotoDecision] = useState<'photo'|'existing'|'new'|'none'|null>(item.photo_decision ?? null);
  const [pdSaving, setPdSaving] = useState(false);

  async function handlePhotoDecision(val: 'photo'|'existing'|'new'|'none') {
    setPdSaving(true);
    try {
      await updateInboundItem(token, item.id, { photo_decision: val });
      setPhotoDecision(val);
      onUpdated();
    } catch { alert('사진처리결정 저장 실패'); }
    finally { setPdSaving(false); }
  }

  // ── inbox 사진 연결 ──
  const [showInboxPicker, setShowInboxPicker] = useState(true);
  const [inboxLinking, setInboxLinking] = useState<string | null>(null);  // 링크 중인 photo id

  async function handleLinkInboxPhoto(inboxPhotoId: string) {
    setInboxLinking(inboxPhotoId);
    try {
      await linkInboxPhotoToItem(token, item.id, inboxPhotoId);
      setPhotoDecision('photo');
      onUpdated();
    } catch (e) {
      alert('사진 연결 실패: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setInboxLinking(null);
    }
  }

  async function handleUnlinkInboxPhoto(inboxPhotoId: string) {
    setInboxLinking(inboxPhotoId);
    try {
      await unlinkInboxPhotoFromItem(token, item.id, inboxPhotoId);
      onUpdated();
    } catch (e) {
      alert('사진 연결 해제 실패: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setInboxLinking(null);
    }
  }

  // ── 품목 미확인 상태 계산 ──
  const needsQtyConfirm = !item.actual_qty_confirmed;
  const needsPhotoDecision = (item.actual_qty >= 1) && (photoDecision === null);
  const hasIssue = needsQtyConfirm || needsPhotoDecision;
  const borderColor = needsQtyConfirm ? '#fb923c' : needsPhotoDecision ? '#ef4444' : C.border;

  // ── render ──────────────────────────
  return (
    <div style={{ ...cardStyle, border: `1px solid ${borderColor}`, borderLeftWidth: hasIssue ? 4 : 1 }}>

      {/* ── 카드 헤더 ── */}
      <div className="tw-border-b tw-border-solid tw-border-[#f3f4f8] tw-pt-[13px] tw-px-[16px] tw-pb-[11px]">
        <div className="tw-items-start tw-flex tw-gap-[10px] tw-justify-between">

          {/* 왼쪽: 품명 */}
          <div className="tw-flex-1 tw-min-w-0">
            <div className="tw-items-center tw-flex tw-gap-[5px] tw-mb-[4px]">
              <span className="tw-text-[#9ca3af] tw-text-[11px] tw-font-semibold">#{item.line_no}</span>
              {saved && <span className="tw-text-[#157347] tw-text-[11px] tw-font-bold">✓ 저장됨</span>}
              {needsQtyConfirm && <span className="tw-bg-[#fff7ed] tw-border tw-border-solid tw-border-[#fb923c] tw-rounded-[5px] tw-text-[#ea580c] tw-text-[10px] tw-font-bold tw-py-[1px] tw-px-[5px]">수량미확인</span>}
            </div>
            <div className="tw-text-tillion-text tw-text-[16px] tw-font-bold tw-leading-[1.3] tw-break-keep">
              {item.item_name || '(품명 없음)'}
            </div>
            {item.option_text && (
              <div className="tw-text-tillion-muted tw-text-[13px] tw-mt-[2px]">{item.option_text}</div>
            )}
            {(item.confirmed_by || item.updated_at) && (
              <div className="tw-flex tw-flex-wrap tw-gap-[8px] tw-mt-[5px]">
                {item.confirmed_by && (
                  <span className="tw-text-tillion-muted tw-text-[10px]">입력: {item.confirmed_by}</span>
                )}
                {item.updated_at && (
                  <span className="tw-text-[#9ca3af] tw-text-[10px]">
                    {item.updated_at.replace('T', ' ').slice(0, 16)}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* 오른쪽: 관리자 버튼 */}
          <div className="tw-items-end tw-flex tw-flex-col tw-shrink-0 tw-gap-[5px]">
            {isAdmin && (
              <div className="tw-flex tw-gap-[4px]">
                <button onClick={() => editMode ? setEditMode(false) : openEditMode()} style={{
                  fontSize: 11, padding: '3px 9px', borderRadius: 6, fontWeight: 600,
                  background: C.borderLight, color: editMode ? C.brand : C.textMuted,
                  border: `1px solid ${C.border}`, cursor: 'pointer',
                }}>
                  {editMode ? '닫기' : '수정'}
                </button>
                {onDelete && (
                  <button
                    onClick={() => { if (confirm(`"${item.item_name || '#' + item.line_no}" 삭제?`)) onDelete?.(); }}
                    className="tw-bg-[#f3f4f8] tw-border tw-border-solid tw-border-tillion-border tw-rounded-[6px] tw-text-tillion-muted tw-cursor-pointer tw-text-[11px] tw-font-semibold tw-py-[3px] tw-px-[9px]"
                  >삭제</button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── 매칭 정보 한 줄 ── */}
      {!editMode && (
        isMatched ? (
          <div className="tw-items-center tw-bg-[#f3f4f8] tw-border-b tw-border-solid tw-border-[#f3f4f8] tw-text-tillion-muted tw-flex tw-flex-wrap tw-text-[12px] tw-gap-y-[2px] tw-gap-x-[8px] tw-py-[6px] tw-px-[16px]">
            <span className="tw-text-[#9ca3af]">공급처</span>
            <span className="tw-text-[#374151] tw-font-semibold">{item.matched_vendor}</span>
            {item.matched_product && <><span className="tw-text-tillion-border">·</span><span>{item.matched_product}</span></>}
            {item.matched_option && <span className="tw-text-[#9ca3af]">/ {item.matched_option}</span>}
            {item.matched_barcode && (
              <span className="tw-text-[#9ca3af] tw-font-mono tw-text-[10px] tw-ml-[4px]">{item.matched_barcode}</span>
            )}
          </div>
        ) : (
          <div className="tw-bg-[#fffdf5] tw-border-b tw-border-solid tw-border-[#f3f4f8] tw-text-[#92400e] tw-text-[12px] tw-py-[6px] tw-px-[16px]">
            ⚠ 미매칭
          </div>
        )
      )}

      {/* ── 관리자 수정 폼 ── */}
      {editMode && (
        <div className="tw-bg-[#f9fafb] tw-border-b tw-border-solid tw-border-tillion-border tw-pt-[12px] tw-px-[16px] tw-pb-[14px]">
          <div className="tw-text-tillion-muted tw-text-[12px] tw-font-bold tw-mb-[10px]">
            품목 수정
          </div>

          {/* 바코드 검색 */}
          <div className="tw-mb-[10px]">
            <div className="tw-text-[#9ca3af] tw-text-[10px] tw-font-semibold tw-mb-[3px]">바코드 검색 (선택 시 품명·옵션 자동입력)</div>
            <div ref={editBarcodeRef} className="tw-relative">
              {editSelectedBarcode ? (
                <div className="tw-items-center tw-flex tw-gap-[6px]">
                  <div className="tw-bg-[#ede9fe] tw-rounded-[8px] tw-text-[#6d28d9] tw-flex-1 tw-text-[12px] tw-font-semibold tw-py-[8px] tw-px-[10px]">
                    ✅ {editSelectedBarcode.바코드} — {editSelectedBarcode.제품명}{editSelectedBarcode.옵션 ? ' / ' + editSelectedBarcode.옵션 : ''}
                  </div>
                  <button onClick={() => { setEditSelectedBarcode(null); setEditBarcodeQuery(''); setEditBarcodeResults([]); }}
                    className="tw-bg-[#f3f4f8] tw-border-0 tw-rounded-[6px] tw-text-tillion-muted tw-cursor-pointer tw-text-[11px] tw-py-[6px] tw-px-[10px]">
                    변경
                  </button>
                </div>
              ) : (
                <>
                  <input
                    value={editBarcodeQuery}
                    onChange={e => handleEditBarcodeInput(e.target.value)}
                    onFocus={() => setEditBarcodeOpen(true)}
                    placeholder="바코드번호 또는 제품명 검색"
                    className="ui-control tw-bg-white"
                  />
                  {editBarcodeLoading && <div className="tw-text-[#9ca3af] tw-text-[11px] tw-py-[3px] tw-px-[2px]">검색 중…</div>}
                  {editBarcodeOpen && editBarcodeResults.length > 0 && (
                    <div className="ops-pop">
                      {editBarcodeResults.map(b => (
                        <div key={b.바코드} onMouseDown={() => selectEditBarcode(b)}
                          className="tw-border-b tw-border-solid tw-border-[#f3f4f8] tw-cursor-pointer tw-py-[8px] tw-px-[12px]">
                          <BarcodeItem b={b} />
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>

          {/* 품명 + 옵션 */}
          <div className="tw-grid tw-gap-[8px] tw-grid-cols-2 tw-mb-[8px]">
            <div>
              <div className="tw-text-[#9ca3af] tw-text-[10px] tw-font-semibold tw-mb-[3px]">품명</div>
              <input
                value={editForm.item_name}
                onChange={e => setEditForm(p => ({ ...p, item_name: e.target.value }))}
                placeholder="품명"
                className="ui-control tw-bg-white"
              />
            </div>
            <div>
              <div className="tw-text-[#9ca3af] tw-text-[10px] tw-font-semibold tw-mb-[3px]">옵션</div>
              <input
                value={editForm.option_text}
                onChange={e => setEditForm(p => ({ ...p, option_text: e.target.value }))}
                placeholder="색상·사이즈 등"
                className="ui-control tw-bg-white"
              />
            </div>
          </div>

          {/* 공급처 위치 + 연락처 */}
          <div className="tw-grid tw-gap-[8px] tw-grid-cols-2 tw-mb-[8px]">
            <div>
              <div className="tw-text-[#9ca3af] tw-text-[10px] tw-font-semibold tw-mb-[3px]">공급처 위치</div>
              <input
                value={editForm.supplier_location}
                onChange={e => setEditForm(p => ({ ...p, supplier_location: e.target.value }))}
                placeholder="예) 동대문 A동 3층"
                className="ui-control tw-bg-white"
              />
            </div>
            <div>
              <div className="tw-text-[#9ca3af] tw-text-[10px] tw-font-semibold tw-mb-[3px]">공급처 연락처</div>
              <input
                value={editForm.supplier_contact}
                onChange={e => setEditForm(p => ({ ...p, supplier_contact: e.target.value }))}
                placeholder="010-0000-0000"
                className="ui-control tw-bg-white"
              />
            </div>
          </div>

          {/* 메모 */}
          <div className="tw-mb-[10px]">
            <div className="tw-text-[#9ca3af] tw-text-[10px] tw-font-semibold tw-mb-[3px]">메모</div>
            <input
              value={editForm.memo}
              onChange={e => setEditForm(p => ({ ...p, memo: e.target.value }))}
              placeholder="메모"
              className="ui-control tw-bg-white"
            />
          </div>

          <div className="tw-flex tw-gap-[8px]">
            <button onClick={handleEditSave} disabled={editSaving} style={{
              flex: 2, height: 40, background: editSaving ? '#d1d5db' : C.brand,
              color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 700, cursor: 'pointer',
            }}>{editSaving ? '저장 중…' : '저장'}</button>
            <button onClick={() => setEditMode(false)} className="tw-bg-white tw-border tw-border-solid tw-border-tillion-border tw-rounded-[8px] tw-text-tillion-muted tw-cursor-pointer tw-flex-1 tw-text-[14px] tw-h-[40px]">취소</button>
          </div>
        </div>
      )}

      {/* ── 수량 + 상태 + 저장 ── */}
      <div className="tw-pt-[14px] tw-px-[16px] tw-pb-[10px]">

        {/* 수량 3칸 — 무채색 레이아웃 */}
        <div className="tw-grid tw-gap-[8px] tw-grid-cols-3 tw-mb-[14px]">
          {/* 장끼 (표시 전용) */}
          <div className="tw-text-center">
            <div className="tw-text-[#9ca3af] tw-text-[10px] tw-font-semibold tw-tracking-[0.3px] tw-mb-[5px]">장끼</div>
            <div className="tw-bg-[#f3f4f8] tw-rounded-[10px] tw-text-[#374151] tw-text-[26px] tw-font-black tw-leading-[1] tw-py-[10px] tw-px-[6px]">{item.janggi_qty}</div>
          </div>
          {/* 실입고 */}
          <div>
            <div className="tw-text-[#9ca3af] tw-text-[10px] tw-font-semibold tw-tracking-[0.3px] tw-mb-[5px] tw-text-center">실입고</div>
            <input
              type="number" inputMode="numeric" min={0}
              value={actualQty}
              onChange={e => setActualQty(Number(e.target.value))}
              className="tw-bg-white tw-border-[1.5px] tw-border-solid tw-border-tillion-border tw-rounded-[10px] tw-box-border tw-text-tillion-text tw-text-[26px] tw-font-black tw-outline-none tw-py-[9px] tw-px-[4px] tw-text-center tw-w-full"
            />
          </div>
          {/* 미입고 */}
          <div>
            <div className="tw-text-[#9ca3af] tw-text-[10px] tw-font-semibold tw-tracking-[0.3px] tw-mb-[5px] tw-text-center">미입고</div>
            <input
              type="number" inputMode="numeric" min={0}
              value={missingQty}
              onChange={e => setMissingQty(Number(e.target.value))}
              style={{
                width: '100%', boxSizing: 'border-box', fontSize: 26, fontWeight: 900,
                textAlign: 'center', padding: '9px 4px',
                border: `1.5px solid ${C.border}`, borderRadius: 10,
                color: missingQty > 0 ? C.danger : C.textMuted, background: '#fff', outline: 'none',
              }}
            />
          </div>
        </div>

        {/* 이름 미입력 */}
        {!isAdmin && !workerName && (
          <div className="tw-bg-[#fffdf5] tw-border tw-border-solid tw-border-[#fde68a] tw-rounded-[8px] tw-text-[#92400e] tw-text-[12px] tw-mb-[8px] tw-py-[7px] tw-px-[12px]">
            ↑ 상단에서 이름을 먼저 입력해주세요
          </div>
        )}

        {/* 저장 버튼 */}
        <button
          onClick={handleSave}
          disabled={saving || (!isAdmin && !workerName)}
          style={{
            width: '100%', height: 48, borderRadius: 10,
            background: saved ? '#15803d' : (saving || (!isAdmin && !workerName)) ? '#d1d5db' : C.brand,
            color: '#fff', border: 'none', fontSize: 15, fontWeight: 700,
            cursor: (saving || (!isAdmin && !workerName)) ? 'not-allowed' : 'pointer',
            marginBottom: 10, transition: 'background 0.2s',
          }}
        >
          {saving ? '저장 중…' : saved ? '✓ 저장됨' : '수량 저장'}
        </button>

        {/* ── 바코드 매칭 섹션 ── */}
        <div className="tw-mb-[8px]">
          <SectionToggle
            open={showMatch}
            label="🔍 상품명 · 도매처 수정 / 바코드 매칭"
            badge={
              item.matched_barcode
                ? <span className="tw-text-[#6d28d9] tw-font-bold">✓ {item.matched_barcode}</span>
                : <span className="tw-text-[#9ca3af]">미매칭</span>
            }
            onToggle={() => {
              setShowMatch(s => !s);
              if (!showMatch) {
                setEditItemName(item.item_name || '');
                setEditWholesale(item.item_wholesale || batchVendor || '');
                setBarcodeQuery(''); setBarcodeResults([]); setAutoMatched(null);
              }
            }}
          />

          {showMatch && (
            <div className="tw-bg-[#fafafa] tw-border tw-border-solid tw-border-tillion-border tw-rounded-[12px] tw-mt-[4px] tw-p-[14px]">
              {/* 상품명·도매처 입력 */}
              <div className="tw-grid tw-gap-[8px] tw-grid-cols-2 tw-mb-[8px]">
                <div>
                  <div className="tw-text-[#9ca3af] tw-text-[10px] tw-font-semibold tw-mb-[3px]">상품명</div>
                  <input value={editItemName} onChange={e => setEditItemName(e.target.value)}
                    placeholder="장끼 상품명" className="ui-control tw-bg-white" />
                </div>
                <div>
                  <div className="tw-text-[#9ca3af] tw-text-[10px] tw-font-semibold tw-mb-[3px]">도매처</div>
                  <input value={editWholesale} onChange={e => setEditWholesale(e.target.value)}
                    placeholder="도매처 (예: NODI)" className="ui-control tw-bg-white" />
                </div>
              </div>

              <div className="tw-flex tw-gap-[6px] tw-mb-[10px]">
                <button onClick={saveItemFields} disabled={nameSaving} style={{
                  flex: 1, height: 36, background: nameSaving ? '#d1d5db' : C.brand,
                  color: '#fff', border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer',
                }}>
                  {nameSaving ? '…' : nameSaved ? '✓ 저장' : '저장'}
                </button>
                <button onClick={() => tryAutoMatch(editItemName, editWholesale)}
                  disabled={barcodeLoading || !editItemName.trim()} style={{
                    flex: 2, height: 36,
                    background: (!editItemName.trim() || barcodeLoading) ? '#d1d5db' : C.textSub,
                    color: '#fff', border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer',
                  }}>
                  {barcodeLoading ? '검색 중…' : '자동매칭 시도'}
                </button>
              </div>

              {/* 자동매칭 1건 */}
              {autoMatched && (
                <div className="tw-bg-white tw-border tw-border-solid tw-border-[#b7ebc9] tw-rounded-[10px] tw-mb-[10px] tw-p-[12px]">
                  <div className="tw-text-[#157347] tw-text-[11px] tw-font-semibold tw-mb-[4px]">✓ 자동매칭 후보</div>
                  <div className="tw-text-tillion-text tw-text-[14px] tw-font-bold">
                    {autoMatched.제품명}{autoMatched.옵션 ? ` / ${autoMatched.옵션}` : ''}
                  </div>
                  <div className="tw-text-[#9ca3af] tw-font-mono tw-text-[11px] tw-mt-[2px] tw-mx-0 tw-mb-[8px]">
                    {autoMatched.바코드}{autoMatched.도매처 && ` · ${autoMatched.도매처}`}
                  </div>
                  <button onClick={() => handleSelectBarcode(autoMatched)} disabled={matchSaving} style={{
                    width: '100%', height: 38, background: matchSaving ? '#d1d5db' : C.brand,
                    color: '#fff', border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer',
                  }}>
                    {matchSaving ? '저장 중…' : '이 바코드로 매칭'}
                  </button>
                </div>
              )}

              {/* 후보 다수 */}
              {!autoMatched && barcodeResults.length > 0 && (
                <div className="tw-mb-[10px]">
                  <div className="tw-text-tillion-muted tw-text-[11px] tw-font-semibold tw-mb-[6px]">
                    후보 {barcodeResults.length}건 — 선택하세요
                  </div>
                  {barcodeResults.map(b => (
                    <button key={b.바코드} onClick={() => handleSelectBarcode(b)} disabled={matchSaving} style={{
                      width: '100%', textAlign: 'left', padding: '9px 12px', marginBottom: 4,
                      borderRadius: 8, background: '#fff', border: `1px solid ${C.border}`,
                      cursor: matchSaving ? 'not-allowed' : 'pointer', display: 'block',
                    }}>
                      <BarcodeItem b={b} />
                    </button>
                  ))}
                </div>
              )}

              {/* 수동 검색 */}
              <div className="tw-border-t tw-border-solid tw-border-[#f3f4f8] tw-pt-[10px]">
                <div className="tw-text-[#9ca3af] tw-text-[10px] tw-font-semibold tw-mb-[5px]">직접 검색</div>
                <input
                  value={barcodeQuery} onChange={e => handleBarcodeInput(e.target.value)}
                  placeholder="바코드 · 제품명 · 도매처 검색"
                  className="ui-control tw-bg-white tw-mb-[4px]"
                />
                {!barcodeLoading && barcodeQuery && barcodeResults.length === 0 && !autoMatched && (
                  <div className="tw-text-tillion-muted tw-text-[12px]">검색 결과 없음</div>
                )}
                {barcodeQuery && barcodeResults.map(b => (
                  <button key={b.바코드} onClick={() => handleSelectBarcode(b)} disabled={matchSaving} className="tw-bg-white tw-border tw-border-solid tw-border-tillion-border tw-rounded-[8px] tw-cursor-pointer tw-block tw-mb-[4px] tw-py-[9px] tw-px-[12px] tw-text-left tw-w-full">
                    <BarcodeItem b={b} />
                  </button>
                ))}
                {matchSaved && <div className="tw-text-[#157347] tw-text-[12px] tw-mt-[4px]">✓ 매칭 저장됨</div>}
              </div>
            </div>
          )}
        </div>

        {/* ── 사진 섹션 ── */}
        <SectionToggle
          open={showPhoto}
          label="📷 제품 사진"
          badge={
            photos.length > 0
              ? <span className="tw-text-tillion-brand tw-font-bold">{photos.length}장</span>
              : <span className="tw-text-[#9ca3af]">없음</span>
          }
          onToggle={() => setShowPhoto(s => !s)}
        />
        {showPhoto && (
          <div className="tw-bg-[#f9fafb] tw-border tw-border-solid tw-border-tillion-border tw-rounded-[12px] tw-mt-[4px] tw-p-[12px]">
            <div className="tw-flex tw-flex-wrap tw-gap-[8px]">
              {photos.map(photo => (
                <div key={photo.id} className="tw-relative">
                  <img
                    src={`${API_BASE}${photo.url}`}
                    alt="제품사진"
                    className="tw-border tw-border-solid tw-border-tillion-border tw-rounded-[10px] tw-cursor-pointer tw-h-[80px] tw-object-cover tw-w-[80px]"
                    onClick={() => window.open(`${API_BASE}${photo.url}`, '_blank')}
                  />
                  {isAdmin && (
                    <button
                      onClick={() => handlePhotoDelete(photo.id)}
                      className="ops-photo-x"
                    >×</button>
                  )}
                </div>
              ))}
              <label style={{
                width: 80, height: 80, borderRadius: 10,
                border: `2px dashed ${C.border}`, background: '#fff',
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                cursor: uploading ? 'wait' : 'pointer', color: C.textFaint, fontSize: 10,
              }}>
                <span className="tw-text-[24px]">{uploading ? '⏳' : '📷'}</span>
                <span className="tw-mt-[2px]">{uploading ? '업로드 중' : '추가'}</span>
                <input type="file" accept="image/*" capture="environment"
                  className="tw-hidden"
                  onChange={handlePhotoUpload} disabled={uploading}
                />
              </label>
            </div>
          </div>
        )}

        {/* ── Inbox 사진 선택 연결 (배치 inbox 사진 전체 표시) ── */}
        {inboxPhotos.length > 0 && (
          <div className="tw-mt-[8px]">
            <button
              onClick={() => setShowInboxPicker(v => !v)}
              style={{
                width: '100%', padding: '7px 12px', borderRadius: 10, fontSize: 12, fontWeight: 600,
                background: showInboxPicker ? '#f0f9ff' : '#f9fafb',
                color: '#0284c7', border: '1px solid #bae6fd',
                cursor: 'pointer', textAlign: 'left',
              }}
            >
              📦 봇 inbox 사진 ({inboxPhotos.length}장 전체 · 이 품목 연결 {photos.filter(p => inboxPhotos.some(ip => ip.stored_filename && p.filename === ip.stored_filename)).length}장)
              {showInboxPicker ? ' ▲' : ' ▼'}
            </button>
            {showInboxPicker && (
              <div className="tw-bg-[#f0f9ff] tw-border tw-border-solid tw-border-[#bae6fd] tw-rounded-[10px] tw-mt-[4px] tw-p-[10px]">
                <div className="tw-text-[#64748b] tw-text-[11px] tw-mb-[8px]">
                  ✅ 이 품목에 연결됨 · 🔗 다른 품목에 연결됨 · 미연결은 클릭하여 연결
                </div>
                <div className="tw-grid tw-gap-[6px] tw-grid-cols-3">
                  {inboxPhotos.map(photo => {
                    // 이 품목에 연결됐는지 (item.photos 와 stored_filename 비교)
                    const linkedToThis = photos.some(p => photo.stored_filename && p.filename === photo.stored_filename);
                    // 다른 품목에 연결됐는지 (matched=true 이지만 이 품목에는 없는 경우)
                    const linkedToOther = photo.matched && !linkedToThis;
                    return (
                      <div
                        key={photo.id}
                        style={{
                          position: 'relative', borderRadius: 8, overflow: 'hidden',
                          border: linkedToThis ? '2px solid #22c55e' : linkedToOther ? '2px solid #f59e0b' : '2px solid #bae6fd',
                          cursor: (linkedToThis || linkedToOther) ? 'not-allowed' : inboxLinking ? 'wait' : 'pointer',
                          opacity: inboxLinking === photo.id ? 0.6 : linkedToOther ? 0.45 : 1,
                          transition: 'opacity 0.15s',
                        }}
                      >
                        <div onClick={() => !inboxLinking && !linkedToThis && !linkedToOther && handleLinkInboxPhoto(photo.id)}>
                          {photo.url ? (
                            <img
                              src={`${API_BASE}${photo.url}`}
                              alt={photo.filename || ''}
                              className="tw-aspect-square tw-block tw-object-cover tw-w-full"
                            />
                          ) : (
                            <div className="tw-items-center tw-aspect-square tw-bg-[#e0f2fe] tw-flex tw-text-[28px] tw-justify-center tw-w-full">📷</div>
                          )}
                          <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, background: linkedToThis ? 'rgba(34,197,94,0.8)' : linkedToOther ? 'rgba(245,158,11,0.8)' : 'rgba(0,0,0,0.5)', padding: '2px 4px', fontSize: 9, color: '#fff', textAlign: 'center' }}>
                            {inboxLinking === photo.id ? '연결 중…' : linkedToThis ? '✅ 연결됨' : linkedToOther ? '🔗 다른품목' : '선택'}
                          </div>
                        </div>
                        {/* 연결 해제 버튼 (이 품목에 연결됐을 때만) */}
                        {linkedToThis && (
                          <button
                            onClick={() => handleUnlinkInboxPhoto(photo.id)}
                            disabled={!!inboxLinking}
                            className="tw-items-center tw-bg-tillion-danger tw-border-0 tw-rounded-full tw-text-white tw-cursor-pointer tw-flex tw-text-[11px] tw-h-[18px] tw-justify-center tw-leading-[1] tw-absolute tw-right-[2px] tw-top-[2px] tw-w-[18px]"
                            title="연결 해제"
                          >×</button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── 사진 처리결정 ── (실입고 1개 이상인 품목에만 표시) */}
        {item.actual_qty >= 1 && (
          <div style={{
            marginTop: 8, padding: '10px 12px',
            background: needsPhotoDecision ? '#fff7ed' : '#f9fafb',
            borderRadius: 12,
            border: `1px solid ${needsPhotoDecision ? '#fb923c' : C.border}`,
          }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: needsPhotoDecision ? '#ea580c' : C.textMuted, marginBottom: 6 }}>
              {needsPhotoDecision ? '⚠️ 사진 처리결정 필요' : '📸 사진 처리결정'}
              {photoDecision && <span className="tw-font-normal tw-ml-[6px]">
                ({photoDecision === 'photo' ? '업로드사진' : photoDecision === 'existing' ? '기존상품' : photoDecision === 'new' ? '신상품' : '사진없음'})
              </span>}
            </div>
            <div className="tw-flex tw-flex-wrap tw-gap-[6px]">
              {(['photo', 'existing', 'new', 'none'] as const).map(v => {
                const labels: Record<string, string> = { photo: '📷 업로드사진', existing: '🔗 기존상품', new: '🆕 신상품', none: '🚫 사진없음' };
                const isActive = photoDecision === v;
                return (
                  <button
                    key={v}
                    disabled={pdSaving}
                    onClick={() => handlePhotoDecision(v)}
                    style={{
                      fontSize: 11, padding: '4px 10px', borderRadius: 8, fontWeight: 600,
                      background: isActive ? C.brand : '#fff',
                      color: isActive ? '#fff' : C.textMuted,
                      border: `1px solid ${isActive ? C.brand : C.border}`,
                      cursor: pdSaving ? 'wait' : 'pointer',
                    }}
                  >{labels[v]}</button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════
// 품목 직접 추가 모달
// ══════════════════════════════════════
function AddItemModal({ token, batchId, batchVendor, onClose, onAdded }: {
  token: string; batchId: string; batchVendor: string;
  onClose: () => void; onAdded: () => void;
}) {
  const [vendorList, setVendorList] = useState<InboundRegisteredVendor[]>([]);
  const [aliasList,  setAliasList]  = useState<VendorAlias[]>([]);
  const [vendorQuery, setVendorQuery] = useState('');
  const [vendorOpen,  setVendorOpen]  = useState(false);
  const [selectedVendors, setSelectedVendors] = useState<string[]>([]);
  const [vendorDisplay,   setVendorDisplay]   = useState('');
  const [barcodeResults, setBarcodeResults] = useState<RepairBarcode[]>([]);
  const [barcodeQuery,   setBarcodeQuery]   = useState('');
  const [barcodeOpen,    setBarcodeOpen]    = useState(false);
  const [barcodeLoading, setBarcodeLoading] = useState(false);
  const [selectedBarcode, setSelectedBarcode] = useState<RepairBarcode | null>(null);
  const [apiSearchResults, setApiSearchResults] = useState<RepairBarcode[]>([]);
  const [apiSearchLoading, setApiSearchLoading] = useState(false);
  const apiSearchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [form, setForm] = useState({ item_name: '', option_text: '', janggi_qty: 1, unit_price: '' });
  const [adding, setAdding] = useState(false);
  const vendorRef  = useRef<HTMLDivElement>(null);
  const barcodeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    Promise.all([listInboundVendors(token), getVendorAliases(token)])
      .then(([v, a]) => {
        setVendorList(v.registered); setAliasList(a.aliases);
        const matched = v.registered.find(r => r.name === batchVendor || r.aliases.includes(batchVendor));
        const aliasM  = a.aliases.find(al => al.canonical === batchVendor);
        if (matched) { setVendorDisplay(matched.name); setVendorQuery(matched.name); setSelectedVendors([matched.name]); }
        else if (aliasM) { setVendorDisplay(aliasM.canonical); setVendorQuery(aliasM.canonical); setSelectedVendors(aliasM.aliases.length > 0 ? aliasM.aliases : [aliasM.canonical]); }
      }).catch(() => {});
  }, [token, batchVendor]);

  useEffect(() => {
    if (selectedVendors.length === 0) { setBarcodeResults([]); return; }
    setBarcodeLoading(true);
    Promise.all(selectedVendors.map(v => getRepairBarcodes({ vendor: v, limit: 300 })))
      .then(results => {
        const seen = new Set<string>();
        setBarcodeResults(results.flatMap(r => r.items).filter(b => { if (seen.has(b.바코드)) return false; seen.add(b.바코드); return true; }));
      }).catch(() => setBarcodeResults([]))
      .finally(() => setBarcodeLoading(false));
  }, [selectedVendors]);

  useEffect(() => {
    function h(e: MouseEvent) {
      if (vendorRef.current  && !vendorRef.current.contains(e.target as Node))  setVendorOpen(false);
      if (barcodeRef.current && !barcodeRef.current.contains(e.target as Node)) setBarcodeOpen(false);
    }
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  function selectVendor(name: string, members: string[]) {
    setVendorDisplay(name); setVendorQuery(name);
    setSelectedVendors(members.length > 0 ? members : [name]);
    setVendorOpen(false); setSelectedBarcode(null); setBarcodeQuery(''); setApiSearchResults([]);
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
    apiSearchTimerRef.current = setTimeout(async () => {
      setApiSearchLoading(true);
      try {
        // 현재 선택된 업체(나블리 alias 해석 결과)만 검색
        const vendorKeys = selectedVendors.length > 0 ? selectedVendors : [];
        if (vendorKeys.length === 0) {
          const r = await getRepairBarcodes({ q: val.trim(), limit: 40 });
          setApiSearchResults(r.items);
        } else {
          const results = await Promise.all(
            vendorKeys.map(v => getRepairBarcodes({ q: val.trim(), vendor: v, limit: 40 }))
          );
          const seen = new Set<string>();
          const merged = results.flatMap(r => r.items).filter(b => {
            if (seen.has(b.바코드)) return false;
            seen.add(b.바코드); return true;
          });
          setApiSearchResults(merged.slice(0, 40));
        }
      }
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
  // 타이핑 중이면 API 전체검색 결과 우선, 아니면 벤더 필터 목록
  const displayBarcodes = barcodeQuery.trim() ? apiSearchResults.slice(0, 40) : fBarcodes.slice(0, 40);

  async function handleAdd() {
    if (!form.item_name.trim()) return;
    setAdding(true);
    try {
      await addInboundItem(token, batchId, {
        item_name: form.item_name.trim(), option_text: form.option_text.trim() || undefined,
        janggi_qty: form.janggi_qty, unit_price: form.unit_price ? Number(form.unit_price) : undefined,
        memo: 'manual',
        matched_barcode: selectedBarcode?.바코드, matched_vendor: selectedBarcode?.업체명,
        matched_product: selectedBarcode?.제품명, matched_option: selectedBarcode?.옵션 || undefined,
      });
      onAdded();
    } catch { alert('품목 추가 실패'); }
    finally { setAdding(false); }
  }

  const inp: React.CSSProperties = { ...inputBase, marginBottom: 0 };
  const lbl: React.CSSProperties = { fontSize: 12, color: C.textMuted, display: 'block', marginBottom: 4, fontWeight: 600 };
  const dropS: React.CSSProperties = {
    position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 400,
    background: '#fff', border: `1px solid ${C.border}`, borderRadius: 10,
    boxShadow: '0 4px 20px rgba(0,0,0,0.12)', maxHeight: 220, overflowY: 'auto', marginTop: 3,
  };

  return (
    <div className="tw-items-end tw-bg-black/50 tw-flex tw-inset-0 tw-justify-center tw-fixed tw-z-[200]" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="ops-sheet">
        {/* handle bar */}
        <div className="tw-bg-tillion-border tw-rounded-[2px] tw-h-[4px] tw-mt-0 tw-mx-auto tw-mb-[16px] tw-w-[40px]" />
        <div className="tw-items-center tw-flex tw-justify-between tw-mb-[18px]">
          <span className="tw-text-[17px] tw-font-extrabold">품목 직접 추가</span>
          <button onClick={onClose} className="tw-items-center tw-bg-[#f3f4f8] tw-border-0 tw-rounded-full tw-text-tillion-muted tw-cursor-pointer tw-flex tw-text-[18px] tw-h-[32px] tw-justify-center tw-w-[32px]">×</button>
        </div>

        {/* 업체 */}
        <label className="ops-label">업체</label>
        <div ref={vendorRef} className="tw-mb-[14px] tw-relative">
          <input value={vendorQuery}
            onChange={e => { setVendorQuery(e.target.value); setVendorOpen(true); if (!e.target.value) { setSelectedVendors([]); setVendorDisplay(''); } }}
            onFocus={() => setVendorOpen(true)}
            placeholder="업체명 또는 별칭 검색"
            className="ui-control" />
          {vendorOpen && (fVendors.length > 0 || fAliases.length > 0) && (
            <div style={dropS}>
              {fVendors.length > 0 && <>
                <div className="tw-bg-[#fafafa] tw-border-b tw-border-solid tw-border-[#f3f4f8] tw-text-[#9ca3af] tw-text-[10px] tw-font-bold tw-py-[5px] tw-px-[12px]">📦 등록 업체</div>
                {fVendors.map(v => (
                  <div key={v.name} onMouseDown={() => selectVendor(v.name, [v.name])}
                    style={{ padding: '9px 14px', fontSize: 14, cursor: 'pointer', borderBottom: `1px solid ${C.borderLight}`, background: vendorDisplay === v.name ? C.brandLight : undefined }}>
                    <strong>{v.name}</strong>
                    {v.aliases.length > 0 && <span className="tw-text-[#9ca3af] tw-text-[11px] tw-ml-[6px]">({v.aliases.join(', ')})</span>}
                  </div>
                ))}
              </>}
              {fAliases.length > 0 && <>
                <div className="tw-bg-[#fafafa] tw-border-b tw-border-solid tw-border-[#f3f4f8] tw-text-[#9ca3af] tw-text-[10px] tw-font-bold tw-py-[5px] tw-px-[12px]">🏷️ 화주사 별칭</div>
                {fAliases.map(a => (
                  <div key={a.canonical} onMouseDown={() => selectVendor(a.canonical, a.aliases)}
                    className="tw-border-b tw-border-solid tw-border-[#f3f4f8] tw-cursor-pointer tw-text-[14px] tw-py-[9px] tw-px-[14px]">
                    <span className="tw-text-tillion-brand tw-font-bold">{a.canonical}</span>
                    {a.aliases.length > 0 && <span className="tw-text-[#9ca3af] tw-text-[11px] tw-ml-[6px]">→ {a.aliases.join(', ')}</span>}
                  </div>
                ))}
              </>}
            </div>
          )}
        </div>

        {/* 바코드 */}
        <label className="ops-label">
          바코드{' '}
          {barcodeLoading ? '(로딩 중…)' : selectedVendors.length > 0 && barcodeResults.length > 0 ? `(${barcodeResults.length}개)` : '(바코드 · 제품명 검색)'}
        </label>
        <div ref={barcodeRef} className="tw-mb-[14px] tw-relative">
          {selectedBarcode ? (
            <div className="tw-items-center tw-flex tw-gap-[8px]">
              <div className="tw-bg-[#ede9fe] tw-rounded-[10px] tw-text-[#6d28d9] tw-flex-1 tw-text-[13px] tw-font-semibold tw-py-[9px] tw-px-[12px]">
                ✅ {selectedBarcode.바코드} — {selectedBarcode.제품명}{selectedBarcode.옵션 ? ' / ' + selectedBarcode.옵션 : ''}
              </div>
              <button onClick={() => { setSelectedBarcode(null); setBarcodeQuery(''); setApiSearchResults([]); }}
                className="tw-bg-[#f3f4f8] tw-border-0 tw-rounded-[8px] tw-text-tillion-muted tw-cursor-pointer tw-text-[12px] tw-py-[7px] tw-px-[12px]">변경</button>
            </div>
          ) : (
            <>
              {!barcodeLoading && selectedVendors.length > 0 && barcodeResults.length === 0 && (
                <div className="tw-bg-[#fdecec] tw-border tw-border-solid tw-border-[#f6c4c4] tw-rounded-[8px] tw-text-[12px] tw-mb-[8px] tw-py-[8px] tw-px-[12px]">
                  <span className="tw-text-[#b42318]">"{vendorDisplay}" 등록 바코드 없음</span>
                  <a href="/journal-settings" target="_blank" rel="noreferrer"
                    className="tw-text-tillion-brand tw-font-bold tw-ml-[8px] tw-underline">+ 신규 등록</a>
                </div>
              )}
              <input
                value={barcodeQuery}
                onChange={e => handleBarcodeQueryChange(e.target.value)}
                onFocus={() => setBarcodeOpen(true)}
                placeholder={selectedVendors.length > 0 && barcodeResults.length > 0 ? `바코드·제품명 검색 (${barcodeResults.length}개)` : '바코드번호 또는 제품명'}
                className="ui-control"
              />
              {(barcodeLoading || apiSearchLoading) && <div className="tw-text-[#9ca3af] tw-text-[11px] tw-py-[3px] tw-px-[2px]">검색 중…</div>}
              {!apiSearchLoading && selectedVendors.length === 0 && barcodeQuery.trim() && apiSearchResults.length === 0 && (
                <div className="tw-text-[#b42318] tw-text-[12px] tw-py-[3px] tw-px-[2px]">검색 결과 없음</div>
              )}
              {barcodeOpen && displayBarcodes.length > 0 && (
                <div style={dropS}>
                  {displayBarcodes.map(b => (
                    <div key={b.바코드} onMouseDown={() => selectBarcode(b)}
                      className="tw-border-b tw-border-solid tw-border-[#f3f4f8] tw-cursor-pointer tw-py-[9px] tw-px-[14px]">
                      <BarcodeItem b={b} />
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {/* 품명 */}
        <label className="ops-label">품명 *</label>
        <input value={form.item_name} onChange={e => setForm(f => ({ ...f, item_name: e.target.value }))}
          placeholder="예) 타원 백팩" style={{ ...inp, marginBottom: 14 }} />

        {/* 옵션 */}
        <label className="ops-label">옵션 (색상·사이즈)</label>
        <input value={form.option_text} onChange={e => setForm(f => ({ ...f, option_text: e.target.value }))}
          placeholder="예) 블랙, L" style={{ ...inp, marginBottom: 14 }} />

        {/* 수량 + 단가 */}
        <div className="tw-grid tw-gap-[12px] tw-grid-cols-2 tw-mb-[22px]">
          <div>
            <label className="ops-label">장끼 수량 *</label>
            <input type="number" inputMode="numeric" min={1} value={form.janggi_qty}
              onChange={e => setForm(f => ({ ...f, janggi_qty: Number(e.target.value) }))}
              style={{ ...inp, fontSize: 20, fontWeight: 800, textAlign: 'center' }} />
          </div>
          <div>
            <label className="ops-label">단가 (선택)</label>
            <input type="number" inputMode="numeric" min={0} value={form.unit_price}
              onChange={e => setForm(f => ({ ...f, unit_price: e.target.value }))}
              placeholder="0" style={{ ...inp, textAlign: 'center' }} />
          </div>
        </div>

        <div className="tw-flex tw-gap-[10px]">
          <button onClick={onClose}
            className="tw-bg-white tw-border tw-border-solid tw-border-tillion-border tw-rounded-[12px] tw-text-tillion-muted tw-cursor-pointer tw-flex-1 tw-text-[15px] tw-font-bold tw-h-[50px]">
            취소
          </button>
          <button onClick={handleAdd} disabled={adding || !form.item_name.trim()}
            style={{
              flex: 2, height: 50, border: 'none',
              background: (adding || !form.item_name.trim()) ? '#d1d5db' : C.brand,
              color: '#fff', borderRadius: 12, fontSize: 15, fontWeight: 800,
              cursor: (adding || !form.item_name.trim()) ? 'not-allowed' : 'pointer',
            }}>
            {adding ? '추가 중…' : '추가'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════
// 메인 페이지
// ══════════════════════════════════════
export default function InboundWorkPage() {
  const { id } = useParams<{ id: string }>();
  const [token,    setToken]   = useState('');
  const [batch,    setBatch]   = useState<InboundBatch | null>(null);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState('');
  const [expired,   setExpired]   = useState(false);
  const [closing,  setClosing] = useState(false);
  const [closeMsg, setCloseMsg] = useState('');
  const [workerName,   setWorkerName]   = useState('');
  const [nameInput,    setNameInput]    = useState('');
  const [showNameEdit, setShowNameEdit] = useState(false);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [ocrMsg,    setOcrMsg]    = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [inboxPhotos,   setInboxPhotos]   = useState<InboundInboxPhoto[]>([]);
  const [showInbox,     setShowInbox]     = useState(true);
  const [grading,       setGrading]       = useState(false);
  const [gradeMsg,      setGradeMsg]      = useState('');
  const [fillingQty,    setFillingQty]    = useState(false);

  const reload = useCallback(async (tok: string) => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await getInboundBatch(tok, id);
      setBatch(data);
      // 봇 수집 제품사진 inbox 로드 (로그인 세션만)
      if (tok) {
        listInboundInboxPhotos(tok, id)
          .then(r => setInboxPhotos(r.photos))
          .catch(() => {});
      }
    } catch (e: unknown) {
      if (e instanceof ApiError && e.status === 410) {
        setExpired(true);
      } else {
        setError('입고 정보를 불러오지 못했습니다.');
      }
    }
    finally { setLoading(false); }
  }, [id]);

  useEffect(() => {
    const tok  = localStorage.getItem('token') || '';
    const name = localStorage.getItem('inbound_worker_name') || '';
    setToken(tok); setWorkerName(name); setNameInput(name);
    reload(tok);
  }, [reload]);

  async function handleOcr(file: File) {
    if (!batch) return;
    setOcrLoading(true); setOcrMsg('');
    try {
      const res = await runInboundOcr(token, batch.id, file);
      await reload(token);
      setOcrMsg(`✅ OCR 완료: ${res.item_count}개 품목 (자동매칭 ${res.matched_count}개)`);
    } catch (e) { setOcrMsg('❌ ' + (e instanceof Error ? e.message : 'OCR 실패')); }
    finally { setOcrLoading(false); }
  }

  async function handleClose(closeType: 'am' | 'pm') {
    if (!batch) return;
    setClosing(true); setCloseMsg('');
    try {
      const res = await closeInboundBatch(token, batch.id, closeType);
      if (!res.ok && res.warning) {
        let msg = '⚠️ ' + res.warning;
        if (res.unconfirmed_items && res.unconfirmed_items.length > 0) {
          msg += '\n미확인 품목: ' + res.unconfirmed_items.map(i => `${i.line_no}번 ${i.item_name || ''}`).join(', ');
        }
        if (res.undecided_photo_items && res.undecided_photo_items.length > 0) {
          msg += '\n사진미결 품목: ' + res.undecided_photo_items.map(i => `${i.line_no}번 ${i.item_name || ''}`).join(', ');
        }
        if (res.defect_qty || res.repair_qty) {
          msg += `\n불량판정중 ${res.defect_qty ?? 0}개, 수선중 ${res.repair_qty ?? 0}개`;
        }
        setCloseMsg(msg);
      }
      else {
        await reload(token);
        if (closeType === 'pm' && res.formula_str) setCloseMsg(`✅ ${res.status_label || '완료'}\n${res.formula_str}`);
        else setCloseMsg('✅ ' + (res.message || res.status_label || '완료'));
      }
    } catch (e) { setCloseMsg('오류: ' + (e instanceof Error ? e.message : String(e))); }
    finally { setClosing(false); }
  }

  /** 검품·양품화 완료: 미처리(pending) 품목을 정상처리(confirmed)로 일괄 이동 */
  async function handleGradeComplete() {
    if (!batch) return;
    if (!window.confirm('미처리 품목을 모두 정상처리로 이동합니다. 불량·수선 처리가 모두 끝난 후 실행해주세요. 계속하시겠습니까?')) return;
    setGrading(true); setGradeMsg('');
    try {
      const res = await gradeCompleteInboundBatch(token, batch.id);
      await reload(token);
      setGradeMsg(res.moved > 0
        ? `✅ 미처리 ${res.moved}건 → 정상처리 완료`
        : '✅ ' + res.message);
    } catch (e) { setGradeMsg('❌ ' + (e instanceof Error ? e.message : '오류 발생')); }
    finally { setGrading(false); }
  }

  /** 수량 전부 장끼와 동일: 모든 품목의 실입고수량을 장끼수량으로 설정 */
  async function handleFillAllJanggi() {
    if (!batch) return;
    const pendingItems = (batch.items || []).filter(i => (i.actual_qty ?? 0) === 0 && (i.janggi_qty ?? 0) > 0);
    if (pendingItems.length === 0) { alert('이미 모든 품목에 수량이 입력되어 있습니다.'); return; }
    if (!window.confirm(`${pendingItems.length}개 품목의 실입고수량을 장끼수량과 동일하게 설정합니다.`)) return;
    setFillingQty(true);
    try {
      await Promise.all(pendingItems.map(item =>
        updateInboundItem(token, item.id, {
          actual_qty:  item.janggi_qty ?? 0,
          missing_qty: 0,
          ...(workerName ? { confirmed_by: workerName } : {}),
        })
      ));
      await reload(token);
    } catch (e) { alert('일부 품목 저장 실패: ' + (e instanceof Error ? e.message : String(e))); }
    finally { setFillingQty(false); }
  }

  function saveName() {
    const name = nameInput.trim();
    setWorkerName(name); localStorage.setItem('inbound_worker_name', name);
    setShowNameEdit(false);
  }

  // ── 로딩 / 에러 화면 ──
  if (expired) return (
    <div className="ops-screen">
      <div className="ops-screen-card">
        <div className="ops-empty-icon">🔒</div>
        <div className="ops-screen-title">링크가 만료되었습니다</div>
        <div className="ops-screen-copy">
          실수량 입력 링크는 <strong>당일 자정</strong>까지만 유효합니다.<br />
          다음 날 접근이 필요하다면 관리자에게 문의하세요.
        </div>
      </div>
    </div>
  );

  if (error) return (
    <div className="ops-screen">
      <div className="ops-screen-card">
        <div className="ops-empty-icon">📦</div>
        <div className="ops-screen-title is-bad">{error}</div>
      </div>
    </div>
  );

  if (loading) return (
    <div className="ops-screen">
      <div className="ops-screen-card">
        <div className="ops-empty-icon">📦</div>
        <div className="ops-screen-title">불러오는 중…</div>
      </div>
    </div>
  );

  if (!batch) return null;

  const isAdmin    = !!token;
  const items      = batch.items || [];
  const doneCount  = items.filter(i => i.status !== 'pending').length;
  const progress   = items.length > 0 ? Math.round((doneCount / items.length) * 100) : 0;
  const canClose        = ['confirming'].includes(batch.status);
  const canGradeComplete = ['inbound_done', 'grading', 'repairing'].includes(batch.status);

  return (
    <div className="ops-work">
      <header className="ops-work-header">
        <div className="ops-work-inner">
          <div className="ops-work-top">
            <div>
              <div className="ops-work-title">📦 {batch.vendor}</div>
              <div className="ops-work-meta">
                {batch.inbound_date}
                {batch.wholesale && ` · ${batch.wholesale}`}
              </div>
            </div>
            <StatusBadge status={batch.status} label={batch.status_label} />
          </div>
          {items.length > 0 && (
            <div className="ops-progress">
              <div className="ops-progress-meta">
                <span>진행률 {doneCount}/{items.length}건 완료</span>
                <span className={progress === 100 ? 'ops-progress-pct is-done' : 'ops-progress-pct'}>{progress}%</span>
              </div>
              <div className="ops-progress-track">
                <div className={progress === 100 ? 'ops-progress-bar is-done' : 'ops-progress-bar'} style={{ width: `${progress}%` }} />
              </div>
            </div>
          )}
        </div>
      </header>

      {!isAdmin && (
        <div className={workerName ? 'ops-worker is-ready' : 'ops-worker'}>
          <div className="ops-work-inner">
            {!workerName || showNameEdit ? (
              <div className="ops-worker-row">
                <span className="ops-worker-label">👤 이름</span>
                <input
                  className="ui-control ops-worker-input"
                  value={nameInput}
                  onChange={e => setNameInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') saveName(); }}
                  placeholder="이름을 입력하세요"
                  autoFocus
                />
                <button onClick={saveName} disabled={!nameInput.trim()} className="ops-worker-ok">확인</button>
              </div>
            ) : (
              <div className="ops-worker-set">
                <span className="ops-worker-name">👤 {workerName}</span>
                <button onClick={() => { setShowNameEdit(true); setNameInput(workerName); }} className="ops-linkish">변경</button>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="ops-qty-band">
        <div className="ops-work-inner ops-qty">
          <div className="ops-qty-cell">
            <div className="ops-qty-label">장끼</div>
            <div className="ops-qty-value">{batch.total_janggi_qty ?? 0}</div>
          </div>
          <div className="ops-qty-cell">
            <div className="ops-qty-label">실입고</div>
            <div className="ops-qty-value is-ok">{batch.total_actual_qty ?? 0}</div>
          </div>
          <div className="ops-qty-cell">
            <div className="ops-qty-label">미입고</div>
            <div className={(batch.total_missing_qty ?? 0) > 0 ? 'ops-qty-value is-bad' : 'ops-qty-value is-muted'}>{batch.total_missing_qty ?? 0}</div>
          </div>
        </div>
      </div>

      {inboxPhotos.length > 0 && (
        <div className="ops-work-inner ops-inbox">
          <SectionToggle
            open={showInbox}
            label={`📦 봇 수집 제품사진 (${inboxPhotos.filter(p => !p.matched).length}장 미매칭 / 총 ${inboxPhotos.length}장)`}
            badge={
              inboxPhotos.some(p => !p.matched)
                ? <Badge variant="warning">매칭필요</Badge>
                : <Badge variant="success">완료</Badge>
            }
            onToggle={() => setShowInbox(v => !v)}
          />
          {showInbox && (
            <div className="ops-card is-pad">
              <div className="ops-photo-grid">
                {inboxPhotos.map(photo => (
                  <div key={photo.id} className={photo.matched ? 'ops-photo is-matched' : 'ops-photo'}>
                    {photo.url ? (
                      <img
                        src={`${API_BASE}${photo.url}`}
                        alt={photo.filename || '제품사진'}
                        onClick={() => window.open(`${API_BASE}${photo.url}`, '_blank')}
                      />
                    ) : (
                      <div className="ops-photo-fallback">📷</div>
                    )}
                    <div className="ops-photo-cap">{photo.matched ? '✅ 매칭완료' : '미매칭'}</div>
                  </div>
                ))}
              </div>
              <div className="ops-help">봇 채팅에서 수집된 제품사진입니다. 품목 편집 → 바코드 선택 시 자동으로 사진 사전에 등록됩니다.</div>
            </div>
          )}
        </div>
      )}

      <div className="ops-work-inner ops-work-body">
        {ocrMsg && (
          <div className={ocrMsg.startsWith('✅') ? 'ops-note is-ok' : 'ops-note is-bad'}>{ocrMsg}</div>
        )}

        {items.length === 0 ? (
          <EmptyState
            className="ops-card"
            icon="📋"
            title={batch.status === 'ocr_pending' ? '장끼 OCR 대기 중' : 'OCR 결과 없음'}
            description={batch.status === 'ocr_pending'
              ? <>아래 버튼으로 장끼 사진을 찍으면<br />AI가 품목을 자동으로 읽어드립니다.</>
              : <>다시 촬영하거나 직접 입력해주세요.</>}
            action={isAdmin ? (
              <div className="ops-stack">
                <label className={ocrLoading ? 'ops-ocr is-busy' : 'ops-ocr'}>
                  {ocrLoading ? '🤖 AI 분석 중… (10~30초)' : '📷 장끼 사진 촬영 → AI 분석'}
                  <input type="file" accept="image/*" capture="environment" className="ops-file"
                    disabled={ocrLoading}
                    onChange={e => { const f = e.target.files?.[0]; if (f) handleOcr(f); e.target.value = ''; }}
                  />
                </label>
                <button onClick={() => setShowAddModal(true)} className="ops-add">➕ 품목 직접 입력</button>
              </div>
            ) : null}
          />
        ) : (
          items.map(item => (
            <ItemCard
              key={item.id}
              item={item}
              token={token}
              workerName={workerName}
              isAdmin={isAdmin}
              batchVendor={batch?.vendor || ''}
              inboxPhotos={inboxPhotos}
              onUpdated={() => reload(token)}
              onDelete={isAdmin ? async () => {
                try { await deleteInboundItem(token, item.id); await reload(token); }
                catch (e) { alert('삭제 실패: ' + (e instanceof Error ? e.message : String(e))); }
              } : undefined}
            />
          ))
        )}

        {isAdmin && items.length > 0 && (
          <div className="ops-choice-row">
            <label className={ocrLoading ? 'ops-ocr is-busy' : 'ops-ocr'}>
              {ocrLoading ? '🤖 AI 분석 중…' : '🔄 장끼 재분석'}
              <input type="file" accept="image/*" capture="environment" className="ops-file"
                disabled={ocrLoading}
                onChange={e => { const f = e.target.files?.[0]; if (f) handleOcr(f); e.target.value = ''; }}
              />
            </label>
            <button onClick={() => setShowAddModal(true)} className="ops-add">➕ 품목 추가</button>
          </div>
        )}

        {isAdmin && canClose && items.length > 0 && (
          <button onClick={handleFillAllJanggi} disabled={fillingQty} className="ops-quiet">
            {fillingQty ? '설정 중…' : '📋 수량 전부 장끼와 동일 (미입력 품목만)'}
          </button>
        )}

        {isAdmin && canClose && (
          <div>
            {closeMsg && (
              <div className={closeMsg.startsWith('✅') ? 'ops-note is-ok' : 'ops-note is-bad'}>{closeMsg}</div>
            )}
            {batch.status === 'confirming' && (
              <button onClick={() => handleClose('am')} disabled={closing} className="ops-finish is-close">
                {closing ? '처리 중…' : '✅ 입고 확인 완료'}
              </button>
            )}
          </div>
        )}

        {isAdmin && canGradeComplete && (
          <div>
            {gradeMsg && (
              <div className={gradeMsg.startsWith('✅') ? 'ops-note is-ok' : 'ops-note is-bad'}>{gradeMsg}</div>
            )}
            <button onClick={handleGradeComplete} disabled={grading} className="ops-finish is-grade">
              {grading ? '처리 중…' : '🔷 검품·양품화 완료'}
            </button>
          </div>
        )}

        {batch.status === 'done' && (
          <div className="ops-done">
            <div className="ops-done-mark">✅</div>
            <div className="ops-done-title">최종 완료</div>
            {batch.closed_by && <div className="ops-help">{batch.closed_by} 마감</div>}
          </div>
        )}
      </div>

      {/* 수동 추가 모달 */}
      {showAddModal && batch && (
        <AddItemModal
          token={token}
          batchId={batch.id}
          batchVendor={batch.vendor}
          onClose={() => setShowAddModal(false)}
          onAdded={async () => { setShowAddModal(false); await reload(token); }}
        />
      )}
    </div>
  );
}
