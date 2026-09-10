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
const BATCH_STATUS_COLOR: Record<string, { bg: string; color: string }> = {
  ocr_pending:  { bg: '#f3f4f6', color: '#374151' },
  confirming:   { bg: '#fef9c3', color: '#92400e' },
  inbound_done: { bg: '#dbeafe', color: '#1d4ed8' },
  grading:      { bg: C.purpleLight, color: C.purple },
  repairing:    { bg: '#ffedd5', color: '#c2410c' },
  done:         { bg: C.successLight, color: C.success },
  cancelled:    { bg: C.dangerLight,  color: C.danger },
};


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
    <button
      onClick={onToggle}
      style={{
        width: '100%', padding: '9px 14px',
        background: '#fff',
        color: C.textMuted,
        border: `1px solid ${C.border}`,
        borderRadius: 10, fontSize: 13, fontWeight: 500,
        cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        transition: 'border-color 0.15s',
      }}
    >
      <span style={{ color: open ? C.textSub : C.textMuted }}>{label}</span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11 }}>
        {badge}
        <span style={{ color: C.textFaint }}>{open ? '▲' : '▼'}</span>
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
      <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>
        {b.제품명}{b.옵션 ? ` / ${b.옵션}` : ''}
      </div>
      {b.상품명 && b.상품명 !== b.제품명 && (
        <div style={{ fontSize: 11, color: C.textMuted, marginTop: 1 }}>
          {b.상품명}
        </div>
      )}
      <div style={{ fontSize: 11, color: C.textFaint, display: 'flex', gap: 8, marginTop: 2, fontFamily: 'monospace' }}>
        <span>{b.바코드}</span>
        {b.도매처 && <span style={{ color: C.purple, fontFamily: 'inherit' }}>{b.도매처}</span>}
        {b.업체명 && <span style={{ color: C.textFaint, fontFamily: 'inherit' }}>[{b.업체명}]</span>}
      </div>
    </>
  );
}

// ══════════════════════════════════════
// 품목 카드
// ══════════════════════════════════════
function ItemCard({ item, token, workerName, isAdmin, batchVendor, onUpdated, onDelete }: {
  item: InboundItem;
  token: string;
  workerName: string;
  isAdmin: boolean;
  batchVendor: string;
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

  // ── render ──────────────────────────
  return (
    <div style={{ ...cardStyle, border: `1px solid ${C.border}` }}>

      {/* ── 카드 헤더 ── */}
      <div style={{ padding: '13px 16px 11px', borderBottom: `1px solid ${C.borderLight}` }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>

          {/* 왼쪽: 품명 */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 4 }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: C.textFaint }}>#{item.line_no}</span>
              {saved && <span style={{ fontSize: 11, color: C.success, fontWeight: 700 }}>✓ 저장됨</span>}
            </div>
            <div style={{ fontSize: 16, fontWeight: 700, color: C.text, lineHeight: 1.3, wordBreak: 'keep-all' }}>
              {item.item_name || '(품명 없음)'}
            </div>
            {item.option_text && (
              <div style={{ fontSize: 13, color: C.textMuted, marginTop: 2 }}>{item.option_text}</div>
            )}
            {(item.confirmed_by || item.updated_at) && (
              <div style={{ display: 'flex', gap: 8, marginTop: 5, flexWrap: 'wrap' }}>
                {item.confirmed_by && (
                  <span style={{ fontSize: 10, color: C.textMuted }}>입력: {item.confirmed_by}</span>
                )}
                {item.updated_at && (
                  <span style={{ fontSize: 10, color: C.textFaint }}>
                    {item.updated_at.replace('T', ' ').slice(0, 16)}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* 오른쪽: 관리자 버튼 */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 5, flexShrink: 0 }}>
            {isAdmin && (
              <div style={{ display: 'flex', gap: 4 }}>
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
                    style={{
                      fontSize: 11, padding: '3px 9px', borderRadius: 6, fontWeight: 600,
                      background: C.borderLight, color: C.textMuted,
                      border: `1px solid ${C.border}`, cursor: 'pointer',
                    }}
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
          <div style={{
            padding: '6px 16px', borderBottom: `1px solid ${C.borderLight}`,
            background: C.borderLight, fontSize: 12, color: C.textMuted,
            display: 'flex', flexWrap: 'wrap', gap: '2px 8px', alignItems: 'center',
          }}>
            <span style={{ color: C.textFaint }}>공급처</span>
            <span style={{ color: C.textSub, fontWeight: 600 }}>{item.matched_vendor}</span>
            {item.matched_product && <><span style={{ color: C.border }}>·</span><span>{item.matched_product}</span></>}
            {item.matched_option && <span style={{ color: C.textFaint }}>/ {item.matched_option}</span>}
            {item.matched_barcode && (
              <span style={{ color: C.textFaint, fontFamily: 'monospace', fontSize: 10, marginLeft: 4 }}>{item.matched_barcode}</span>
            )}
          </div>
        ) : (
          <div style={{
            padding: '6px 16px', borderBottom: `1px solid ${C.borderLight}`,
            background: '#fffdf5', fontSize: 12, color: '#92400e',
          }}>
            ⚠ 미매칭
          </div>
        )
      )}

      {/* ── 관리자 수정 폼 ── */}
      {editMode && (
        <div style={{ padding: '12px 16px 14px', background: '#f9fafb', borderBottom: `1px solid ${C.border}` }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: C.textMuted, marginBottom: 10 }}>
            품목 수정
          </div>

          {/* 바코드 검색 */}
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 10, color: C.textFaint, fontWeight: 600, marginBottom: 3 }}>바코드 검색 (선택 시 품명·옵션 자동입력)</div>
            <div ref={editBarcodeRef} style={{ position: 'relative' }}>
              {editSelectedBarcode ? (
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <div style={{ flex: 1, padding: '8px 10px', background: C.purpleLight, borderRadius: 8, fontSize: 12, color: C.purple, fontWeight: 600 }}>
                    ✅ {editSelectedBarcode.바코드} — {editSelectedBarcode.제품명}{editSelectedBarcode.옵션 ? ' / ' + editSelectedBarcode.옵션 : ''}
                  </div>
                  <button onClick={() => { setEditSelectedBarcode(null); setEditBarcodeQuery(''); setEditBarcodeResults([]); }}
                    style={{ padding: '6px 10px', background: C.borderLight, border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 11, color: C.textMuted }}>
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
                    style={{ ...inputBase, background: '#fff' }}
                  />
                  {editBarcodeLoading && <div style={{ fontSize: 11, color: C.textFaint, padding: '3px 2px' }}>검색 중…</div>}
                  {editBarcodeOpen && editBarcodeResults.length > 0 && (
                    <div style={{
                      position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 300,
                      background: '#fff', border: `1px solid ${C.border}`, borderRadius: 8,
                      boxShadow: '0 4px 16px rgba(0,0,0,0.1)', maxHeight: 200, overflowY: 'auto', marginTop: 2,
                    }}>
                      {editBarcodeResults.map(b => (
                        <div key={b.바코드} onMouseDown={() => selectEditBarcode(b)}
                          style={{ padding: '8px 12px', cursor: 'pointer', borderBottom: `1px solid ${C.borderLight}` }}>
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
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
            <div>
              <div style={{ fontSize: 10, color: C.textFaint, fontWeight: 600, marginBottom: 3 }}>품명</div>
              <input
                value={editForm.item_name}
                onChange={e => setEditForm(p => ({ ...p, item_name: e.target.value }))}
                placeholder="품명"
                style={{ ...inputBase, background: '#fff' }}
              />
            </div>
            <div>
              <div style={{ fontSize: 10, color: C.textFaint, fontWeight: 600, marginBottom: 3 }}>옵션</div>
              <input
                value={editForm.option_text}
                onChange={e => setEditForm(p => ({ ...p, option_text: e.target.value }))}
                placeholder="색상·사이즈 등"
                style={{ ...inputBase, background: '#fff' }}
              />
            </div>
          </div>

          {/* 공급처 위치 + 연락처 */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
            <div>
              <div style={{ fontSize: 10, color: C.textFaint, fontWeight: 600, marginBottom: 3 }}>공급처 위치</div>
              <input
                value={editForm.supplier_location}
                onChange={e => setEditForm(p => ({ ...p, supplier_location: e.target.value }))}
                placeholder="예) 동대문 A동 3층"
                style={{ ...inputBase, background: '#fff' }}
              />
            </div>
            <div>
              <div style={{ fontSize: 10, color: C.textFaint, fontWeight: 600, marginBottom: 3 }}>공급처 연락처</div>
              <input
                value={editForm.supplier_contact}
                onChange={e => setEditForm(p => ({ ...p, supplier_contact: e.target.value }))}
                placeholder="010-0000-0000"
                style={{ ...inputBase, background: '#fff' }}
              />
            </div>
          </div>

          {/* 메모 */}
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 10, color: C.textFaint, fontWeight: 600, marginBottom: 3 }}>메모</div>
            <input
              value={editForm.memo}
              onChange={e => setEditForm(p => ({ ...p, memo: e.target.value }))}
              placeholder="메모"
              style={{ ...inputBase, background: '#fff' }}
            />
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={handleEditSave} disabled={editSaving} style={{
              flex: 2, height: 40, background: editSaving ? '#d1d5db' : C.brand,
              color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 700, cursor: 'pointer',
            }}>{editSaving ? '저장 중…' : '저장'}</button>
            <button onClick={() => setEditMode(false)} style={{
              flex: 1, height: 40, background: '#fff', border: `1px solid ${C.border}`,
              borderRadius: 8, fontSize: 14, color: C.textMuted, cursor: 'pointer',
            }}>취소</button>
          </div>
        </div>
      )}

      {/* ── 수량 + 상태 + 저장 ── */}
      <div style={{ padding: '14px 16px 10px' }}>

        {/* 수량 3칸 — 무채색 레이아웃 */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 14 }}>
          {/* 장끼 (표시 전용) */}
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 10, color: C.textFaint, fontWeight: 600, marginBottom: 5, letterSpacing: 0.3 }}>장끼</div>
            <div style={{
              background: C.borderLight, borderRadius: 10, padding: '10px 6px',
              fontSize: 26, fontWeight: 900, color: C.textSub, lineHeight: 1,
            }}>{item.janggi_qty}</div>
          </div>
          {/* 실입고 */}
          <div>
            <div style={{ fontSize: 10, color: C.textFaint, fontWeight: 600, textAlign: 'center', marginBottom: 5, letterSpacing: 0.3 }}>실입고</div>
            <input
              type="number" inputMode="numeric" min={0}
              value={actualQty}
              onChange={e => setActualQty(Number(e.target.value))}
              style={{
                width: '100%', boxSizing: 'border-box', fontSize: 26, fontWeight: 900,
                textAlign: 'center', padding: '9px 4px',
                border: `1.5px solid ${C.border}`, borderRadius: 10,
                color: C.text, background: '#fff', outline: 'none',
              }}
            />
          </div>
          {/* 미입고 */}
          <div>
            <div style={{ fontSize: 10, color: C.textFaint, fontWeight: 600, textAlign: 'center', marginBottom: 5, letterSpacing: 0.3 }}>미입고</div>
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
          <div style={{ marginBottom: 8, padding: '7px 12px', borderRadius: 8, background: '#fffdf5', border: `1px solid #fde68a`, fontSize: 12, color: '#92400e' }}>
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
        <div style={{ marginBottom: 8 }}>
          <SectionToggle
            open={showMatch}
            label="🔍 상품명 · 도매처 수정 / 바코드 매칭"
            badge={
              item.matched_barcode
                ? <span style={{ color: C.purple, fontWeight: 700 }}>✓ {item.matched_barcode}</span>
                : <span style={{ color: C.textFaint }}>미매칭</span>
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
            <div style={{
              marginTop: 4, padding: 14,
              background: '#fafafa', borderRadius: 12, border: `1px solid ${C.border}`,
            }}>
              {/* 상품명·도매처 입력 */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
                <div>
                  <div style={{ fontSize: 10, color: C.textFaint, fontWeight: 600, marginBottom: 3 }}>상품명</div>
                  <input value={editItemName} onChange={e => setEditItemName(e.target.value)}
                    placeholder="장끼 상품명" style={{ ...inputBase, background: '#fff' }} />
                </div>
                <div>
                  <div style={{ fontSize: 10, color: C.textFaint, fontWeight: 600, marginBottom: 3 }}>도매처</div>
                  <input value={editWholesale} onChange={e => setEditWholesale(e.target.value)}
                    placeholder="도매처 (예: NODI)" style={{ ...inputBase, background: '#fff' }} />
                </div>
              </div>

              <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
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
                <div style={{
                  marginBottom: 10, padding: 12,
                  background: '#fff', border: `1px solid ${C.successBorder}`, borderRadius: 10,
                }}>
                  <div style={{ fontSize: 11, color: C.success, fontWeight: 600, marginBottom: 4 }}>✓ 자동매칭 후보</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: C.text }}>
                    {autoMatched.제품명}{autoMatched.옵션 ? ` / ${autoMatched.옵션}` : ''}
                  </div>
                  <div style={{ fontSize: 11, color: C.textFaint, margin: '2px 0 8px', fontFamily: 'monospace' }}>
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
                <div style={{ marginBottom: 10 }}>
                  <div style={{ fontSize: 11, color: C.textMuted, fontWeight: 600, marginBottom: 6 }}>
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
              <div style={{ borderTop: `1px solid ${C.borderLight}`, paddingTop: 10 }}>
                <div style={{ fontSize: 10, color: C.textFaint, fontWeight: 600, marginBottom: 5 }}>직접 검색</div>
                <input
                  value={barcodeQuery} onChange={e => handleBarcodeInput(e.target.value)}
                  placeholder="바코드 · 제품명 · 도매처 검색"
                  style={{ ...inputBase, background: '#fff', marginBottom: 4 }}
                />
                {!barcodeLoading && barcodeQuery && barcodeResults.length === 0 && !autoMatched && (
                  <div style={{ fontSize: 12, color: C.textMuted }}>검색 결과 없음</div>
                )}
                {barcodeQuery && barcodeResults.map(b => (
                  <button key={b.바코드} onClick={() => handleSelectBarcode(b)} disabled={matchSaving} style={{
                    width: '100%', textAlign: 'left', padding: '9px 12px', marginBottom: 4,
                    borderRadius: 8, background: '#fff', border: `1px solid ${C.border}`,
                    cursor: 'pointer', display: 'block',
                  }}>
                    <BarcodeItem b={b} />
                  </button>
                ))}
                {matchSaved && <div style={{ fontSize: 12, color: C.success, marginTop: 4 }}>✓ 매칭 저장됨</div>}
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
              ? <span style={{ color: C.brand, fontWeight: 700 }}>{photos.length}장</span>
              : <span style={{ color: C.textFaint }}>없음</span>
          }
          onToggle={() => setShowPhoto(s => !s)}
        />
        {showPhoto && (
          <div style={{
            marginTop: 4, padding: 12,
            background: '#f9fafb', borderRadius: 12, border: `1px solid ${C.border}`,
          }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {photos.map(photo => (
                <div key={photo.id} style={{ position: 'relative' }}>
                  <img
                    src={`${API_BASE}${photo.url}`}
                    alt="제품사진"
                    style={{ width: 80, height: 80, objectFit: 'cover', borderRadius: 10, border: `1px solid ${C.border}`, cursor: 'pointer' }}
                    onClick={() => window.open(`${API_BASE}${photo.url}`, '_blank')}
                  />
                  {isAdmin && (
                    <button
                      onClick={() => handlePhotoDelete(photo.id)}
                      style={{
                        position: 'absolute', top: -5, right: -5,
                        width: 22, height: 22, borderRadius: '50%',
                        background: C.danger, color: '#fff', border: 'none',
                        fontSize: 13, cursor: 'pointer',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        boxShadow: '0 1px 4px rgba(0,0,0,0.3)',
                      }}
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
                <span style={{ fontSize: 24 }}>{uploading ? '⏳' : '📷'}</span>
                <span style={{ marginTop: 2 }}>{uploading ? '업로드 중' : '추가'}</span>
                <input type="file" accept="image/*" capture="environment"
                  style={{ display: 'none' }}
                  onChange={handlePhotoUpload} disabled={uploading}
                />
              </label>
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
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
      zIndex: 200, display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
    }} onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{
        background: '#fff', borderRadius: '20px 20px 0 0',
        padding: '20px 18px 40px', width: '100%', maxWidth: 520,
        maxHeight: '90vh', overflowY: 'auto',
        boxShadow: '0 -4px 30px rgba(0,0,0,0.15)',
      }}>
        {/* handle bar */}
        <div style={{ width: 40, height: 4, background: C.border, borderRadius: 2, margin: '0 auto 16px' }} />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
          <span style={{ fontWeight: 800, fontSize: 17 }}>품목 직접 추가</span>
          <button onClick={onClose} style={{ background: C.borderLight, border: 'none', width: 32, height: 32, borderRadius: '50%', fontSize: 18, cursor: 'pointer', color: C.textMuted, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>×</button>
        </div>

        {/* 업체 */}
        <label style={lbl}>업체</label>
        <div ref={vendorRef} style={{ position: 'relative', marginBottom: 14 }}>
          <input value={vendorQuery}
            onChange={e => { setVendorQuery(e.target.value); setVendorOpen(true); if (!e.target.value) { setSelectedVendors([]); setVendorDisplay(''); } }}
            onFocus={() => setVendorOpen(true)}
            placeholder="업체명 또는 별칭 검색"
            style={inp} />
          {vendorOpen && (fVendors.length > 0 || fAliases.length > 0) && (
            <div style={dropS}>
              {fVendors.length > 0 && <>
                <div style={{ padding: '5px 12px', fontSize: 10, color: C.textFaint, fontWeight: 700, background: '#fafafa', borderBottom: `1px solid ${C.borderLight}` }}>📦 등록 업체</div>
                {fVendors.map(v => (
                  <div key={v.name} onMouseDown={() => selectVendor(v.name, [v.name])}
                    style={{ padding: '9px 14px', fontSize: 14, cursor: 'pointer', borderBottom: `1px solid ${C.borderLight}`, background: vendorDisplay === v.name ? C.brandLight : undefined }}>
                    <strong>{v.name}</strong>
                    {v.aliases.length > 0 && <span style={{ fontSize: 11, color: C.textFaint, marginLeft: 6 }}>({v.aliases.join(', ')})</span>}
                  </div>
                ))}
              </>}
              {fAliases.length > 0 && <>
                <div style={{ padding: '5px 12px', fontSize: 10, color: C.textFaint, fontWeight: 700, background: '#fafafa', borderBottom: `1px solid ${C.borderLight}` }}>🏷️ 화주사 별칭</div>
                {fAliases.map(a => (
                  <div key={a.canonical} onMouseDown={() => selectVendor(a.canonical, a.aliases)}
                    style={{ padding: '9px 14px', fontSize: 14, cursor: 'pointer', borderBottom: `1px solid ${C.borderLight}` }}>
                    <span style={{ fontWeight: 700, color: C.brand }}>{a.canonical}</span>
                    {a.aliases.length > 0 && <span style={{ fontSize: 11, color: C.textFaint, marginLeft: 6 }}>→ {a.aliases.join(', ')}</span>}
                  </div>
                ))}
              </>}
            </div>
          )}
        </div>

        {/* 바코드 */}
        <label style={lbl}>
          바코드{' '}
          {barcodeLoading ? '(로딩 중…)' : selectedVendors.length > 0 && barcodeResults.length > 0 ? `(${barcodeResults.length}개)` : '(바코드 · 제품명 검색)'}
        </label>
        <div ref={barcodeRef} style={{ position: 'relative', marginBottom: 14 }}>
          {selectedBarcode ? (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <div style={{ flex: 1, padding: '9px 12px', background: C.purpleLight, borderRadius: 10, fontSize: 13, color: C.purple, fontWeight: 600 }}>
                ✅ {selectedBarcode.바코드} — {selectedBarcode.제품명}{selectedBarcode.옵션 ? ' / ' + selectedBarcode.옵션 : ''}
              </div>
              <button onClick={() => { setSelectedBarcode(null); setBarcodeQuery(''); setApiSearchResults([]); }}
                style={{ padding: '7px 12px', background: C.borderLight, border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 12, color: C.textMuted }}>변경</button>
            </div>
          ) : (
            <>
              {!barcodeLoading && selectedVendors.length > 0 && barcodeResults.length === 0 && (
                <div style={{ marginBottom: 8, padding: '8px 12px', background: C.dangerLight, border: `1px solid ${C.dangerBorder}`, borderRadius: 8, fontSize: 12 }}>
                  <span style={{ color: C.danger }}>"{vendorDisplay}" 등록 바코드 없음</span>
                  <a href="/journal-settings" target="_blank" rel="noreferrer"
                    style={{ marginLeft: 8, color: C.brand, fontWeight: 700, textDecoration: 'underline' }}>+ 신규 등록</a>
                </div>
              )}
              <input
                value={barcodeQuery}
                onChange={e => handleBarcodeQueryChange(e.target.value)}
                onFocus={() => setBarcodeOpen(true)}
                placeholder={selectedVendors.length > 0 && barcodeResults.length > 0 ? `바코드·제품명 검색 (${barcodeResults.length}개)` : '바코드번호 또는 제품명'}
                style={inp}
              />
              {(barcodeLoading || apiSearchLoading) && <div style={{ fontSize: 11, color: C.textFaint, padding: '3px 2px' }}>검색 중…</div>}
              {!apiSearchLoading && selectedVendors.length === 0 && barcodeQuery.trim() && apiSearchResults.length === 0 && (
                <div style={{ fontSize: 12, color: C.danger, padding: '3px 2px' }}>검색 결과 없음</div>
              )}
              {barcodeOpen && displayBarcodes.length > 0 && (
                <div style={dropS}>
                  {displayBarcodes.map(b => (
                    <div key={b.바코드} onMouseDown={() => selectBarcode(b)}
                      style={{ padding: '9px 14px', cursor: 'pointer', borderBottom: `1px solid ${C.borderLight}` }}>
                      <BarcodeItem b={b} />
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {/* 품명 */}
        <label style={lbl}>품명 *</label>
        <input value={form.item_name} onChange={e => setForm(f => ({ ...f, item_name: e.target.value }))}
          placeholder="예) 타원 백팩" style={{ ...inp, marginBottom: 14 }} />

        {/* 옵션 */}
        <label style={lbl}>옵션 (색상·사이즈)</label>
        <input value={form.option_text} onChange={e => setForm(f => ({ ...f, option_text: e.target.value }))}
          placeholder="예) 블랙, L" style={{ ...inp, marginBottom: 14 }} />

        {/* 수량 + 단가 */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 22 }}>
          <div>
            <label style={lbl}>장끼 수량 *</label>
            <input type="number" inputMode="numeric" min={1} value={form.janggi_qty}
              onChange={e => setForm(f => ({ ...f, janggi_qty: Number(e.target.value) }))}
              style={{ ...inp, fontSize: 20, fontWeight: 800, textAlign: 'center' }} />
          </div>
          <div>
            <label style={lbl}>단가 (선택)</label>
            <input type="number" inputMode="numeric" min={0} value={form.unit_price}
              onChange={e => setForm(f => ({ ...f, unit_price: e.target.value }))}
              placeholder="0" style={{ ...inp, textAlign: 'center' }} />
          </div>
        </div>

        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={onClose}
            style={{ flex: 1, height: 50, border: `1px solid ${C.border}`, background: '#fff', borderRadius: 12, fontSize: 15, fontWeight: 700, cursor: 'pointer', color: C.textMuted }}>
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
  const [showInbox,     setShowInbox]     = useState(false);
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
      if (!res.ok && res.warning) { setCloseMsg('⚠️ ' + res.warning); }
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
    <div style={{ minHeight: '100vh', background: C.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
      <div style={{ background: '#fff', borderRadius: 20, padding: 32, textAlign: 'center', maxWidth: 340, boxShadow: '0 4px 24px rgba(0,0,0,0.09)' }}>
        <div style={{ fontSize: 56, marginBottom: 16 }}>🔒</div>
        <div style={{ fontSize: 17, fontWeight: 800, color: C.text, marginBottom: 8 }}>링크가 만료되었습니다</div>
        <div style={{ fontSize: 13, color: C.textMuted, lineHeight: 1.7 }}>
          실수량 입력 링크는 <strong>당일 자정</strong>까지만 유효합니다.<br />
          다음 날 접근이 필요하다면 관리자에게 문의하세요.
        </div>
      </div>
    </div>
  );

  if (error) return (
    <div style={{ minHeight: '100vh', background: C.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
      <div style={{ background: '#fff', borderRadius: 16, padding: 28, textAlign: 'center', maxWidth: 320, boxShadow: '0 4px 20px rgba(0,0,0,0.08)' }}>
        <div style={{ fontSize: 48, marginBottom: 12 }}>📦</div>
        <div style={{ color: C.danger, fontSize: 14, fontWeight: 600 }}>{error}</div>
      </div>
    </div>
  );

  if (loading) return (
    <div style={{ minHeight: '100vh', background: C.bg, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ textAlign: 'center', color: C.textMuted }}>
        <div style={{ fontSize: 40, marginBottom: 10 }}>📦</div>
        <div style={{ fontWeight: 600 }}>불러오는 중…</div>
      </div>
    </div>
  );

  if (!batch) return null;

  const isAdmin    = !!token;
  const items      = batch.items || [];
  const doneCount  = items.filter(i => i.status !== 'pending').length;
  const progress   = items.length > 0 ? Math.round((doneCount / items.length) * 100) : 0;
  const statusC    = BATCH_STATUS_COLOR[batch.status] || { bg: C.borderLight, color: C.textSub };
  const canClose        = ['confirming'].includes(batch.status);
  const canGradeComplete = ['inbound_done', 'grading', 'repairing'].includes(batch.status);

  return (
    <div style={{ minHeight: '100vh', background: C.bg, fontFamily: "'Noto Sans KR', -apple-system, sans-serif" }}>

      {/* ── 헤더 ── */}
      <header style={{
        position: 'sticky', top: 0, zIndex: 100,
        background: 'linear-gradient(135deg, #1a1740 0%, #2d2a6b 100%)',
        color: '#fff', padding: '13px 16px 11px',
        boxShadow: '0 2px 12px rgba(26,23,64,0.4)',
      }}>
        <div style={{ maxWidth: 640, margin: '0 auto' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 17, fontWeight: 800, lineHeight: 1.2, letterSpacing: '-0.3px' }}>
                📦 {batch.vendor}
              </div>
              <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.55)', marginTop: 3 }}>
                {batch.inbound_date}
                {batch.wholesale && ` · ${batch.wholesale}`}
              </div>
            </div>
            <span style={{
              flexShrink: 0, padding: '5px 13px', borderRadius: 20,
              fontSize: 12, fontWeight: 700,
              background: statusC.bg, color: statusC.color,
            }}>
              {batch.status_label}
            </span>
          </div>

          {items.length > 0 && (
            <div style={{ marginTop: 11 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'rgba(255,255,255,0.6)', marginBottom: 5 }}>
                <span>진행률 {doneCount}/{items.length}건 완료</span>
                <span style={{ fontWeight: 700, color: progress === 100 ? '#4ade80' : 'rgba(255,255,255,0.8)' }}>{progress}%</span>
              </div>
              <div style={{ height: 5, background: 'rgba(255,255,255,0.15)', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{
                  height: '100%', width: `${progress}%`,
                  background: progress === 100 ? '#4ade80' : '#818cf8',
                  borderRadius: 3, transition: 'width 0.4s ease',
                }} />
              </div>
            </div>
          )}
        </div>
      </header>

      {/* ── 작업자 이름 배너 (비로그인) ── */}
      {!isAdmin && (
        <div style={{
          background: workerName ? '#f0fdf4' : C.warningLight,
          borderBottom: `2px solid ${workerName ? C.successBorder : C.warningBorder}`,
        }}>
          <div style={{ maxWidth: 640, margin: '0 auto', padding: '10px 16px' }}>
            {!workerName || showNameEdit ? (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: C.warning, whiteSpace: 'nowrap' }}>👤 이름</span>
                <input
                  value={nameInput}
                  onChange={e => setNameInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') saveName(); }}
                  placeholder="이름을 입력하세요"
                  autoFocus
                  style={{
                    flex: 1, height: 38, padding: '0 12px', borderRadius: 10,
                    border: `2px solid ${C.warningBorder}`, fontSize: 14, outline: 'none',
                    background: '#fff',
                  }}
                />
                <button onClick={saveName} disabled={!nameInput.trim()} style={{
                  height: 38, padding: '0 16px', background: nameInput.trim() ? C.brand : '#d1d5db',
                  color: '#fff', border: 'none', borderRadius: 10,
                  fontSize: 13, fontWeight: 700, cursor: nameInput.trim() ? 'pointer' : 'not-allowed',
                  whiteSpace: 'nowrap',
                }}>확인</button>
              </div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 13, color: C.success, fontWeight: 700 }}>👤 {workerName}</span>
                <button onClick={() => { setShowNameEdit(true); setNameInput(workerName); }}
                  style={{ fontSize: 12, color: C.textMuted, background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>
                  변경
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── 수량 요약 ── */}
      <div style={{ background: '#fff', borderBottom: `1px solid ${C.borderLight}` }}>
        <div style={{ maxWidth: 640, margin: '0 auto', padding: '12px 16px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
            {[
              { label: '장끼',   value: batch.total_janggi_qty  ?? 0, color: C.textSub  },
              { label: '실입고', value: batch.total_actual_qty  ?? 0, color: C.success  },
              { label: '미입고', value: batch.total_missing_qty ?? 0, color: (batch.total_missing_qty ?? 0) > 0 ? C.danger : C.textFaint },
            ].map(s => (
              <div key={s.label} style={{ textAlign: 'center', padding: '10px 4px', background: C.borderLight, borderRadius: 10 }}>
                <div style={{ fontSize: 10, color: C.textFaint, fontWeight: 600, letterSpacing: 0.5, marginBottom: 3 }}>{s.label}</div>
                <div style={{ fontSize: 24, fontWeight: 900, color: s.color, lineHeight: 1 }}>{s.value}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── 봇 수집 제품사진 inbox ── */}
      {inboxPhotos.length > 0 && (
        <div style={{ maxWidth: 640, margin: '0 auto', padding: '8px 14px 0' }}>
          <SectionToggle
            open={showInbox}
            label={`📦 봇 수집 제품사진 (${inboxPhotos.filter(p => !p.matched).length}장 미매칭 / 총 ${inboxPhotos.length}장)`}
            badge={
              inboxPhotos.some(p => !p.matched)
                ? <span style={{ background: C.warningLight, color: C.warning, borderRadius: 8, padding: '1px 6px', fontSize: 11, fontWeight: 700 }}>매칭필요</span>
                : <span style={{ background: C.successLight, color: C.success, borderRadius: 8, padding: '1px 6px', fontSize: 11, fontWeight: 700 }}>완료</span>
            }
            onToggle={() => setShowInbox(v => !v)}
          />
          {showInbox && (
            <div style={{ ...cardStyle, marginTop: 4, padding: 12 }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                {inboxPhotos.map(photo => (
                  <div key={photo.id} style={{
                    position: 'relative', borderRadius: 10, overflow: 'hidden',
                    border: `2px solid ${photo.matched ? C.successBorder : C.warningBorder}`,
                    background: photo.matched ? C.successLight : C.warningLight,
                  }}>
                    {photo.url ? (
                      <img
                        src={`${API_BASE}${photo.url}`}
                        alt={photo.filename || '제품사진'}
                        style={{ width: '100%', aspectRatio: '1', objectFit: 'cover', display: 'block', cursor: 'pointer' }}
                        onClick={() => window.open(`${API_BASE}${photo.url}`, '_blank')}
                      />
                    ) : (
                      <div style={{ width: '100%', aspectRatio: '1', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 32 }}>📷</div>
                    )}
                    <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, background: 'rgba(0,0,0,0.5)', padding: '3px 5px', fontSize: 10, color: '#fff', textAlign: 'center' }}>
                      {photo.matched ? '✅ 매칭완료' : '미매칭'}
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 8, fontSize: 12, color: C.textMuted, lineHeight: 1.6 }}>
                봇 채팅에서 수집된 제품사진입니다. 품목 편집 → 바코드 선택 시 자동으로 사진 사전에 등록됩니다.
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── 품목 목록 ── */}
      <div style={{ maxWidth: 640, margin: '0 auto', padding: '12px 14px' }}>

        {/* OCR 메시지 */}
        {ocrMsg && (
          <div style={{
            marginBottom: 12, padding: '11px 14px', borderRadius: 12, fontSize: 13, fontWeight: 600,
            background: ocrMsg.startsWith('✅') ? C.successLight : C.dangerLight,
            color:      ocrMsg.startsWith('✅') ? C.success : C.danger,
            border: `1px solid ${ocrMsg.startsWith('✅') ? C.successBorder : C.dangerBorder}`,
          }}>
            {ocrMsg}
          </div>
        )}

        {items.length === 0 ? (
          /* ─ 빈 상태 ─ */
          <div style={{
            ...cardStyle, padding: '32px 20px', textAlign: 'center',
          }}>
            <div style={{ fontSize: 48, marginBottom: 14 }}>📋</div>
            {batch.status === 'ocr_pending' ? (
              <>
                <div style={{ fontSize: 15, fontWeight: 800, color: C.text, marginBottom: 6 }}>장끼 OCR 대기 중</div>
                <div style={{ fontSize: 13, color: C.textMuted, lineHeight: 1.7 }}>
                  아래 버튼으로 장끼 사진을 찍으면<br />AI가 품목을 자동으로 읽어드립니다.
                </div>
              </>
            ) : (
              <>
                <div style={{ fontSize: 15, fontWeight: 800, color: C.text, marginBottom: 6 }}>OCR 결과 없음</div>
                <div style={{ fontSize: 13, color: C.textMuted, lineHeight: 1.7 }}>
                  다시 촬영하거나 직접 입력해주세요.
                </div>
              </>
            )}

            {isAdmin && (
              <div style={{ marginTop: 20, display: 'flex', flexDirection: 'column', gap: 10 }}>
                <label style={{
                  display: 'block', padding: '14px',
                  background: ocrLoading ? '#d1d5db' : '#a16207',
                  color: '#fff', borderRadius: 12, fontSize: 15, fontWeight: 700,
                  cursor: ocrLoading ? 'not-allowed' : 'pointer', textAlign: 'center',
                  boxShadow: ocrLoading ? 'none' : '0 4px 12px rgba(161,98,7,0.3)',
                }}>
                  {ocrLoading ? '🤖 AI 분석 중… (10~30초)' : '📷 장끼 사진 촬영 → AI 분석'}
                  <input type="file" accept="image/*" capture="environment" style={{ display: 'none' }}
                    disabled={ocrLoading}
                    onChange={e => { const f = e.target.files?.[0]; if (f) handleOcr(f); e.target.value = ''; }}
                  />
                </label>
                <button onClick={() => setShowAddModal(true)} style={{
                  padding: '12px', background: C.brandLight, color: C.brand,
                  border: `2px solid ${C.brandBorder}`, borderRadius: 12, fontSize: 14, fontWeight: 700, cursor: 'pointer',
                }}>
                  ➕ 품목 직접 입력
                </button>
              </div>
            )}
          </div>
        ) : (
          /* ─ 품목 카드 목록 ─ */
          items.map(item => (
            <ItemCard
              key={item.id}
              item={item}
              token={token}
              workerName={workerName}
              isAdmin={isAdmin}
              batchVendor={batch?.vendor || ''}
              onUpdated={() => reload(token)}
              onDelete={isAdmin ? async () => {
                try { await deleteInboundItem(token, item.id); await reload(token); }
                catch (e) { alert('삭제 실패: ' + (e instanceof Error ? e.message : String(e))); }
              } : undefined}
            />
          ))
        )}

        {/* ── 관리자 액션 (품목 있을 때) ── */}
        {isAdmin && items.length > 0 && (
          <div style={{ display: 'flex', gap: 8, marginTop: 4, marginBottom: 4 }}>
            <label style={{
              flex: 1, height: 48, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              background: ocrLoading ? '#d1d5db' : C.warningLight,
              color: ocrLoading ? C.textMuted : C.warning,
              border: `2px dashed ${C.warningBorder}`, borderRadius: 12,
              fontSize: 13, fontWeight: 700, cursor: ocrLoading ? 'not-allowed' : 'pointer',
            }}>
              {ocrLoading ? '🤖 AI 분석 중…' : '🔄 장끼 재분석'}
              <input type="file" accept="image/*" capture="environment" style={{ display: 'none' }}
                disabled={ocrLoading}
                onChange={e => { const f = e.target.files?.[0]; if (f) handleOcr(f); e.target.value = ''; }}
              />
            </label>
            <button onClick={() => setShowAddModal(true)} style={{
              flex: 1, height: 48, background: C.brandLight, color: C.brand,
              border: `2px dashed ${C.brandBorder}`, borderRadius: 12,
              fontSize: 13, fontWeight: 700, cursor: 'pointer',
            }}>
              ➕ 품목 추가
            </button>
          </div>
        )}

        {/* ── 수량 전부 장끼와 동일 (관리자, 수량 입력 단계) ── */}
        {isAdmin && canClose && items.length > 0 && (
          <div style={{ marginBottom: 4 }}>
            <button
              onClick={handleFillAllJanggi}
              disabled={fillingQty}
              style={{
                width: '100%', height: 40,
                background: fillingQty ? '#d1d5db' : C.borderLight,
                color: fillingQty ? C.textFaint : C.textSub,
                border: `1px solid ${C.border}`, borderRadius: 10,
                fontSize: 13, fontWeight: 600, cursor: fillingQty ? 'not-allowed' : 'pointer',
              }}
            >
              {fillingQty ? '설정 중…' : '📋 수량 전부 장끼와 동일 (미입력 품목만)'}
            </button>
          </div>
        )}

        {/* ── 입고 확인 완료 버튼 (관리자, confirming 상태) ── */}
        {isAdmin && canClose && (
          <div style={{ paddingTop: 4, paddingBottom: 20 }}>
            {closeMsg && (
              <div style={{
                marginBottom: 12, padding: '11px 14px', borderRadius: 12, fontSize: 13, fontWeight: 600, whiteSpace: 'pre-line',
                background: closeMsg.startsWith('✅') ? C.successLight : C.dangerLight,
                color:      closeMsg.startsWith('✅') ? C.success : C.danger,
                border: `1px solid ${closeMsg.startsWith('✅') ? C.successBorder : C.dangerBorder}`,
              }}>
                {closeMsg}
              </div>
            )}

            {batch.status === 'confirming' && (
              <button onClick={() => handleClose('am')} disabled={closing} style={{
                width: '100%', height: 54,
                background: closing ? '#d1d5db' : '#0369a1', color: '#fff',
                border: 'none', borderRadius: 14, fontSize: 16, fontWeight: 800,
                cursor: closing ? 'not-allowed' : 'pointer',
                boxShadow: closing ? 'none' : '0 4px 16px rgba(3,105,161,0.35)',
                letterSpacing: '-0.3px',
              }}>
                {closing ? '처리 중…' : '✅ 입고 확인 완료'}
              </button>
            )}
          </div>
        )}

        {/* ── 검품·양품화 완료 버튼 (관리자, inbound_done/grading/repairing 상태) ── */}
        {isAdmin && canGradeComplete && (
          <div style={{ paddingTop: 4, paddingBottom: 20 }}>
            {gradeMsg && (
              <div style={{
                marginBottom: 12, padding: '11px 14px', borderRadius: 12, fontSize: 13, fontWeight: 600,
                background: gradeMsg.startsWith('✅') ? C.successLight : C.dangerLight,
                color:      gradeMsg.startsWith('✅') ? C.success : C.danger,
                border: `1px solid ${gradeMsg.startsWith('✅') ? C.successBorder : C.dangerBorder}`,
              }}>
                {gradeMsg}
              </div>
            )}
            <button onClick={handleGradeComplete} disabled={grading} style={{
              width: '100%', height: 54,
              background: grading ? '#d1d5db' : '#5b21b6', color: '#fff',
              border: 'none', borderRadius: 14, fontSize: 16, fontWeight: 800,
              cursor: grading ? 'not-allowed' : 'pointer',
              boxShadow: grading ? 'none' : '0 4px 16px rgba(91,33,182,0.35)',
              letterSpacing: '-0.3px',
            }}>
              {grading ? '처리 중…' : '🔷 검품·양품화 완료'}
            </button>
          </div>
        )}

        {/* ── 완료 상태 ── */}
        {batch.status === 'done' && (
          <div style={{ padding: '28px 0', textAlign: 'center' }}>
            <div style={{ fontSize: 56 }}>✅</div>
            <div style={{ fontSize: 17, fontWeight: 800, color: C.success, marginTop: 10 }}>최종 완료</div>
            {batch.closed_by && (
              <div style={{ fontSize: 12, color: C.textMuted, marginTop: 4 }}>{batch.closed_by} 마감</div>
            )}
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
