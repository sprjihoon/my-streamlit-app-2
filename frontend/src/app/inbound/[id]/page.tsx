'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { useParams } from 'next/navigation';
import {
  getInboundBatch,
  addInboundItem,
  updateInboundItem,
  deleteInboundItem,
  closeInboundBatch,
  runInboundOcr,
  listInboundVendors,
  getRepairBarcodes,
  getVendorAliases,
  InboundBatch,
  InboundItem,
  InboundRegisteredVendor,
  VendorAlias,
  RepairBarcode,
} from '@/lib/api';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ─────────────────────────────────────
// 유틸
// ─────────────────────────────────────

function getToken() {
  if (typeof window === 'undefined') return '';
  return localStorage.getItem('token') || '';
}

function inboundAuthHeaders(token: string) {
  return { Authorization: `Bearer ${token}` };
}

// ─────────────────────────────────────
// 상태 색상
// ─────────────────────────────────────

const BATCH_STATUS_COLOR: Record<string, { bg: string; color: string }> = {
  ocr_pending:  { bg: '#f3f4f6', color: '#6b7280' },
  confirming:   { bg: '#fef9c3', color: '#a16207' },
  inbound_done: { bg: '#dbeafe', color: '#1d4ed8' },
  grading:      { bg: '#ede9fe', color: '#7c3aed' },
  repairing:    { bg: '#ffedd5', color: '#c2410c' },
  done:         { bg: '#dcfce7', color: '#15803d' },
  cancelled:    { bg: '#fee2e2', color: '#dc2626' },
};

const ITEM_STATUS_OPTS: { value: string; label: string; color: string }[] = [
  { value: 'pending',       label: '확인 전',    color: '#6b7280' },
  { value: 'confirmed',     label: '정상',       color: '#15803d' },
  { value: 'missing',       label: '미입고',     color: '#dc2626' },
  { value: 'defect',        label: '불량',       color: '#c2410c' },
  { value: 'repair',        label: '수선대기',   color: '#a16207' },
  { value: 'unrecoverable', label: '회생불가',   color: '#991b1b' },
  { value: 'etc',           label: '기타',       color: '#7c3aed' },
];

// ─────────────────────────────────────
// 품목 카드 컴포넌트
// ─────────────────────────────────────

function ItemCard({ item, token, workerName, isAdmin, onUpdated, onDelete }: {
  item: InboundItem;
  token: string;
  workerName: string;
  isAdmin: boolean;
  onUpdated: () => void;
  onDelete?: () => void;
}) {
  const [actualQty, setActualQty] = useState(item.actual_qty);
  const [missingQty, setMissingQty] = useState(item.missing_qty);
  const [status, setStatus] = useState(item.status);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [photos, setPhotos] = useState(item.photos || []);
  const [saved, setSaved] = useState(false);

  // 수정 모드
  const [editMode, setEditMode] = useState(false);
  const [editForm, setEditForm] = useState({
    item_name: item.item_name || '',
    option_text: item.option_text || '',
    matched_barcode: item.matched_barcode || '',
    matched_vendor: item.matched_vendor || '',
    matched_product: item.matched_product || '',
    matched_option: item.matched_option || '',
    supplier_location: item.supplier_location || '',
    supplier_contact: item.supplier_contact || '',
    memo: item.memo || '',
  });
  const [editSaving, setEditSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    setSaved(false);
    try {
      const autoStatus = actualQty > 0 ? 'confirmed' : missingQty > 0 ? 'missing' : status;
      await updateInboundItem(token, item.id, {
        actual_qty: actualQty,
        missing_qty: missingQty,
        status: autoStatus,
        ...(workerName ? { confirmed_by: workerName } : {}),
      });
      setStatus(autoStatus);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      onUpdated();
    } catch {
      alert('저장 실패');
    } finally {
      setSaving(false);
    }
  }

  async function handleStatusChange(newStatus: string) {
    setStatus(newStatus);
    setSaving(true);
    try {
      await updateInboundItem(token, item.id, {
        status: newStatus,
        ...(workerName ? { confirmed_by: workerName } : {}),
      });
      onUpdated();
    } catch {
      alert('상태 변경 실패');
    } finally {
      setSaving(false);
    }
  }

  async function handleEditSave() {
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

  async function handlePhotoUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch(`${API_BASE}/inbound/items/${item.id}/photos`, {
        method: 'POST',
        headers: inboundAuthHeaders(token),
        body: form,
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setPhotos(prev => [...prev, data]);
    } catch (err) {
      alert('사진 업로드 실패: ' + (err instanceof Error ? err.message : String(err)));
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  }

  async function handlePhotoDelete(photoId: string, filename: string) {
    if (!confirm('사진을 삭제하시겠습니까?')) return;
    try {
      await fetch(`${API_BASE}/inbound/items/${item.id}/photos/${photoId}`, {
        method: 'DELETE',
        headers: inboundAuthHeaders(token),
      });
      setPhotos(prev => prev.filter(p => p.id !== photoId));
    } catch {
      alert('삭제 실패');
    }
  }

  const statusInfo = ITEM_STATUS_OPTS.find(o => o.value === status);
  const needsAttention = status === 'pending';

  const inputS: React.CSSProperties = {
    width: '100%', padding: '8px 10px', border: '1px solid #e5e7f0',
    borderRadius: 8, fontSize: 14, boxSizing: 'border-box',
  };
  const labelS: React.CSSProperties = { fontSize: 11, color: '#9ca3af', display: 'block', marginBottom: 3 };

  return (
    <div style={{
      background: '#fff',
      borderRadius: 12,
      marginBottom: 12,
      border: needsAttention ? '2px solid #fbbf24' : '1px solid #e5e7f0',
      overflow: 'hidden',
      boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
    }}>
      {/* 헤더 */}
      <div style={{
        padding: '12px 14px 8px',
        borderBottom: '1px solid #f3f4f6',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 11, color: '#9ca3af', fontWeight: 600 }}>#{item.line_no}</span>
            {saved && <span style={{ fontSize: 11, color: '#15803d', background: '#dcfce7', padding: '1px 8px', borderRadius: 10 }}>저장됨 ✓</span>}
          </div>
          <div style={{ fontSize: 15, fontWeight: 600, marginTop: 2 }}>{item.item_name || '(품명 없음)'}</div>
          {item.option_text && <div style={{ fontSize: 13, color: '#6b7280', marginTop: 1 }}>{item.option_text}</div>}
          <div style={{ display: 'flex', gap: 8, marginTop: 2, flexWrap: 'wrap' }}>
            {item.confirmed_by && (
              <span style={{ fontSize: 10, color: '#4361ee', background: '#eef2ff', padding: '1px 6px', borderRadius: 8 }}>
                입력: {item.confirmed_by}
              </span>
            )}
            {item.updated_at && (
              <span style={{ fontSize: 10, color: '#d1d5db' }}>
                {item.updated_at.replace('T', ' ').slice(0, 16)}
              </span>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
          <div style={{
            padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600,
            background: (BATCH_STATUS_COLOR[status]?.bg || '#f3f4f6'),
            color: (BATCH_STATUS_COLOR[status]?.color || '#6b7280'),
            whiteSpace: 'nowrap',
          }}>
            {statusInfo?.label || status}
          </div>
          {isAdmin && (
            <>
              <button
                onClick={() => setEditMode(m => !m)}
                style={{
                  fontSize: 11, padding: '3px 9px', borderRadius: 8,
                  background: editMode ? '#4361ee' : '#f3f4f6',
                  color: editMode ? '#fff' : '#6b7280',
                  border: 'none', cursor: 'pointer', fontWeight: 600,
                }}
              >
                ✏️ {editMode ? '닫기' : '수정'}
              </button>
              {onDelete && (
                <button
                  onClick={() => { if (confirm(`"${item.item_name || item.line_no + '번'}" 품목을 삭제하시겠습니까?`)) onDelete(); }}
                  style={{
                    fontSize: 11, padding: '3px 9px', borderRadius: 8,
                    background: '#fef2f2', color: '#dc2626',
                    border: '1px solid #fecaca', cursor: 'pointer', fontWeight: 600,
                  }}
                >🗑 삭제</button>
              )}
            </>
          )}
        </div>
      </div>

      {/* 매칭/공급처 정보 */}
      {!editMode && (
        <>
          {item.matched_product ? (
            <div style={{ padding: '8px 14px', background: '#f8f9fc', fontSize: 12, borderBottom: '1px solid #f3f4f6' }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 12px' }}>
                <span><span style={{ color: '#9ca3af' }}>공급처: </span><span style={{ color: '#7c3aed', fontWeight: 600 }}>{item.matched_vendor}</span></span>
                <span><span style={{ color: '#9ca3af' }}>상품명: </span>{item.matched_product}</span>
                {item.matched_option && <span><span style={{ color: '#9ca3af' }}>옵션: </span>{item.matched_option}</span>}
                {item.matched_barcode && <span style={{ fontFamily: 'monospace', color: '#9ca3af' }}>바코드: {item.matched_barcode}</span>}
              </div>
              {(item.supplier_location || item.supplier_contact) && (
                <div style={{ display: 'flex', gap: 12, marginTop: 4 }}>
                  {item.supplier_location && <span><span style={{ color: '#9ca3af' }}>위치: </span>{item.supplier_location}</span>}
                  {item.supplier_contact && <span><span style={{ color: '#9ca3af' }}>연락처: </span>{item.supplier_contact}</span>}
                </div>
              )}
            </div>
          ) : (
            <div style={{ padding: '6px 14px', background: '#fef2f2', fontSize: 12, color: '#dc2626', borderBottom: '1px solid #f3f4f6' }}>
              ⚠️ 미매칭 — 수정 버튼으로 상품 정보를 직접 입력해주세요
            </div>
          )}
        </>
      )}

      {/* ── 수정 폼 ── */}
      {editMode && (
        <div style={{ padding: '12px 14px', background: '#f0f4ff', borderBottom: '1px solid #e0e7ff' }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: '#4361ee', marginBottom: 10 }}>✏️ 품목 정보 수정</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
            <div>
              <label style={labelS}>바코드</label>
              <input value={editForm.matched_barcode} onChange={e => setEditForm(f => ({ ...f, matched_barcode: e.target.value }))} style={inputS} placeholder="바코드" />
            </div>
            <div>
              <label style={labelS}>공급처(업체명)</label>
              <input value={editForm.matched_vendor} onChange={e => setEditForm(f => ({ ...f, matched_vendor: e.target.value }))} style={inputS} placeholder="공급처" />
            </div>
            <div>
              <label style={labelS}>공급처 상품명</label>
              <input value={editForm.matched_product} onChange={e => setEditForm(f => ({ ...f, matched_product: e.target.value }))} style={inputS} placeholder="공급처 상품명" />
            </div>
            <div>
              <label style={labelS}>공급처 옵션</label>
              <input value={editForm.matched_option} onChange={e => setEditForm(f => ({ ...f, matched_option: e.target.value }))} style={inputS} placeholder="공급처 옵션" />
            </div>
            <div>
              <label style={labelS}>공급처 위치</label>
              <input value={editForm.supplier_location} onChange={e => setEditForm(f => ({ ...f, supplier_location: e.target.value }))} style={inputS} placeholder="예) 동대문 A동 3층" />
            </div>
            <div>
              <label style={labelS}>공급처 연락처</label>
              <input value={editForm.supplier_contact} onChange={e => setEditForm(f => ({ ...f, supplier_contact: e.target.value }))} style={inputS} placeholder="예) 010-0000-0000" />
            </div>
          </div>
          <div style={{ marginBottom: 8 }}>
            <label style={labelS}>메모</label>
            <input value={editForm.memo} onChange={e => setEditForm(f => ({ ...f, memo: e.target.value }))} style={inputS} placeholder="메모" />
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={handleEditSave}
              disabled={editSaving}
              style={{ flex: 2, padding: '10px', background: editSaving ? '#9ca3af' : '#4361ee', color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 700, cursor: 'pointer' }}
            >
              {editSaving ? '저장 중…' : '수정 저장'}
            </button>
            <button
              onClick={() => setEditMode(false)}
              style={{ flex: 1, padding: '10px', background: '#fff', border: '1px solid #e5e7f0', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer', color: '#6b7280' }}
            >
              취소
            </button>
          </div>
        </div>
      )}

      {/* 수량 입력 */}
      <div style={{ padding: '12px 14px' }}>
        <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
          {/* 장끼수량 */}
          <div style={{ textAlign: 'center', flex: 1 }}>
            <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 4 }}>장끼수량</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#1d4ed8' }}>{item.janggi_qty}</div>
          </div>
          {/* 실입고 */}
          <div style={{ flex: 1.5 }}>
            <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 4 }}>실입고 수량</div>
            <input
              type="number" inputMode="numeric" min={0}
              value={actualQty}
              onChange={e => setActualQty(Number(e.target.value))}
              style={{
                width: '100%', fontSize: 20, fontWeight: 700, textAlign: 'center',
                padding: '6px 8px', border: '2px solid #e5e7f0', borderRadius: 8, color: '#15803d',
              }}
            />
          </div>
          {/* 미입고 */}
          <div style={{ flex: 1.5 }}>
            <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 4 }}>미입고 수량</div>
            <input
              type="number" inputMode="numeric" min={0}
              value={missingQty}
              onChange={e => setMissingQty(Number(e.target.value))}
              style={{
                width: '100%', fontSize: 20, fontWeight: 700, textAlign: 'center',
                padding: '6px 8px', border: '2px solid #e5e7f0', borderRadius: 8, color: '#dc2626',
              }}
            />
          </div>
        </div>

        {/* 처리상태 버튼 그룹 */}
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 6 }}>처리상태</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {ITEM_STATUS_OPTS.map(opt => (
              <button
                key={opt.value}
                onClick={() => handleStatusChange(opt.value)}
                disabled={saving}
                style={{
                  padding: '5px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600,
                  border: status === opt.value ? `2px solid ${opt.color}` : '1px solid #e5e7f0',
                  background: status === opt.value ? opt.color + '18' : '#fff',
                  color: status === opt.value ? opt.color : '#6b7280',
                  cursor: 'pointer',
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* 저장 버튼 (비로그인 시 이름 필수) */}
        {!isAdmin && !workerName && (
          <div style={{ marginBottom: 10, padding: '8px 12px', background: '#fffbeb', borderRadius: 8, fontSize: 12, color: '#a16207', border: '1px solid #fbbf24' }}>
            ↑ 상단에서 이름을 먼저 입력해주세요
          </div>
        )}
        <button
          onClick={handleSave}
          disabled={saving || (!isAdmin && !workerName)}
          style={{
            width: '100%', padding: '12px', borderRadius: 8,
            background: (saving || (!isAdmin && !workerName)) ? '#9ca3af' : '#4361ee',
            color: '#fff', border: 'none', fontSize: 15, fontWeight: 600,
            cursor: (saving || (!isAdmin && !workerName)) ? 'not-allowed' : 'pointer',
            marginBottom: 10,
          }}
        >
          {saving ? '저장 중…' : '수량 저장'}
        </button>

        {/* 제품 사진 (관리자만) */}
        {isAdmin && (
          <div>
            <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 6 }}>제품 사진</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
              {photos.map((photo) => (
                <div key={photo.id} style={{ position: 'relative' }}>
                  <img
                    src={`${API_BASE}${photo.url}?t=${getToken()}`}
                    alt="제품사진"
                    style={{ width: 72, height: 72, objectFit: 'cover', borderRadius: 8, border: '1px solid #e5e7f0' }}
                    onClick={() => window.open(`${API_BASE}${photo.url}`, '_blank')}
                  />
                  <button
                    onClick={() => handlePhotoDelete(photo.id, photo.filename)}
                    style={{
                      position: 'absolute', top: -6, right: -6,
                      width: 20, height: 20, borderRadius: '50%',
                      background: '#dc2626', color: '#fff', border: 'none',
                      fontSize: 12, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}
                  >
                    ×
                  </button>
                </div>
              ))}
              <label style={{
                width: 72, height: 72, borderRadius: 8,
                border: '2px dashed #e5e7f0', background: '#f8f9fc',
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                cursor: uploading ? 'wait' : 'pointer', color: '#9ca3af', fontSize: 10,
              }}>
                <span style={{ fontSize: 22 }}>{uploading ? '⏳' : '📷'}</span>
                <span>{uploading ? '업로드 중' : '사진 추가'}</span>
                <input
                  type="file" accept="image/*" capture="environment"
                  style={{ display: 'none' }}
                  onChange={handlePhotoUpload}
                  disabled={uploading}
                />
              </label>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────
// 품목 직접 추가 모달 (모바일 bottom sheet)
// ─────────────────────────────────────

function AddItemModal({ token, batchId, batchVendor, onClose, onAdded }: {
  token: string; batchId: string; batchVendor: string;
  onClose: () => void; onAdded: () => void;
}) {
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

  // 업체/별칭 로드 + 배치 업체 자동 선택
  useEffect(() => {
    Promise.all([listInboundVendors(token), getVendorAliases(token)])
      .then(([v, a]) => {
        setVendorList(v.registered);
        setAliasList(a.aliases);
        const matched = v.registered.find(r => r.name === batchVendor || r.aliases.includes(batchVendor));
        const aliasMatched = a.aliases.find(al => al.canonical === batchVendor);
        if (matched) { setVendorDisplay(matched.name); setVendorQuery(matched.name); setSelectedVendors([matched.name]); }
        else if (aliasMatched) { setVendorDisplay(aliasMatched.canonical); setVendorQuery(aliasMatched.canonical); setSelectedVendors(aliasMatched.aliases.length > 0 ? aliasMatched.aliases : [aliasMatched.canonical]); }
      })
      .catch(() => {});
  }, [token, batchVendor]);

  // 바코드 로드
  useEffect(() => {
    if (selectedVendors.length === 0) { setBarcodeResults([]); return; }
    setBarcodeLoading(true);
    Promise.all(selectedVendors.map(v => getRepairBarcodes({ vendor: v, limit: 300 })))
      .then(results => {
        const seen = new Set<string>();
        setBarcodeResults(results.flatMap(r => r.items).filter(b => { if (seen.has(b.바코드)) return false; seen.add(b.바코드); return true; }));
      })
      .catch(() => setBarcodeResults([]))
      .finally(() => setBarcodeLoading(false));
  }, [selectedVendors]);

  // 외부 클릭
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
  const fbq = (selectedBarcode ? '' : barcodeQuery).toLowerCase();
  const fBarcodes = barcodeResults.filter(b =>
    b.바코드.toLowerCase().includes(fbq) || b.제품명.toLowerCase().includes(fbq) ||
    (b.옵션 || '').toLowerCase().includes(fbq) || b.업체명.toLowerCase().includes(fbq)
  );

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
      onAdded();
    } catch {
      alert('품목 추가 실패');
    } finally {
      setAdding(false);
    }
  }

  const inputS: React.CSSProperties = { width: '100%', padding: '10px 12px', border: '1px solid #e5e7f0', borderRadius: 8, fontSize: 14, boxSizing: 'border-box' };
  const lbl: React.CSSProperties = { fontSize: 12, color: '#6b7280', display: 'block', marginBottom: 4 };
  const dropS: React.CSSProperties = {
    position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 400,
    background: '#fff', border: '1px solid #e5e7f0', borderRadius: 8,
    boxShadow: '0 4px 16px rgba(0,0,0,0.12)', maxHeight: 200, overflowY: 'auto', marginTop: 2,
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 200, display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}
      onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{ background: '#fff', borderRadius: '16px 16px 0 0', padding: '20px 18px 36px', width: '100%', maxWidth: 480, maxHeight: '88vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <span style={{ fontWeight: 700, fontSize: 16 }}>품목 직접 추가</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: 22, cursor: 'pointer', color: '#6b7280', lineHeight: 1 }}>×</button>
        </div>

        {/* 업체 */}
        <label style={lbl}>업체</label>
        <div ref={vendorRef} style={{ position: 'relative', marginBottom: 12 }}>
          <input value={vendorQuery}
            onChange={e => { setVendorQuery(e.target.value); setVendorOpen(true); if (!e.target.value) { setSelectedVendors([]); setVendorDisplay(''); } }}
            onFocus={() => setVendorOpen(true)}
            placeholder="업체명 또는 별칭 검색"
            style={inputS} />
          {vendorOpen && (fVendors.length > 0 || fAliases.length > 0) && (
            <div style={dropS}>
              {fVendors.length > 0 && (
                <>
                  <div style={{ padding: '4px 10px', fontSize: 10, color: '#9ca3af', fontWeight: 700, background: '#fafafa' }}>📦 등록 업체</div>
                  {fVendors.map(v => (
                    <div key={v.name} onMouseDown={() => selectVendor(v.name, [v.name])}
                      style={{ padding: '8px 12px', fontSize: 13, cursor: 'pointer', background: vendorDisplay === v.name ? '#eef2ff' : undefined }}>
                      <strong>{v.name}</strong>
                      {v.aliases.length > 0 && <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 6 }}>({v.aliases.join(', ')})</span>}
                    </div>
                  ))}
                </>
              )}
              {fAliases.length > 0 && (
                <>
                  <div style={{ padding: '4px 10px', fontSize: 10, color: '#9ca3af', fontWeight: 700, background: '#fafafa' }}>🏷️ 화주사 별칭</div>
                  {fAliases.map(a => (
                    <div key={a.canonical} onMouseDown={() => selectVendor(a.canonical, a.aliases)}
                      style={{ padding: '8px 12px', fontSize: 13, cursor: 'pointer' }}>
                      <span style={{ fontWeight: 600, color: '#1d4ed8' }}>{a.canonical}</span>
                      {a.aliases.length > 0 && <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 6 }}>→ {a.aliases.join(', ')}</span>}
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>

        {/* 바코드 */}
        <label style={lbl}>바코드 검색 {barcodeLoading ? '(로딩 중…)' : selectedVendors.length > 0 ? `(${barcodeResults.length}개)` : ''}</label>
        {selectedVendors.length === 0 ? (
          <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 12 }}>↑ 업체를 먼저 선택하세요.</div>
        ) : barcodeLoading ? (
          <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 12 }}>바코드 불러오는 중…</div>
        ) : barcodeResults.length === 0 ? (
          <div style={{ marginBottom: 12, padding: '10px 12px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, fontSize: 13 }}>
            <div style={{ color: '#dc2626', marginBottom: 6 }}>"{vendorDisplay}" 등록 바코드 없음</div>
            <a href="/journal-settings" target="_blank" rel="noreferrer"
              style={{ display: 'inline-block', padding: '5px 12px', background: '#4361ee', color: '#fff', borderRadius: 6, fontSize: 12, textDecoration: 'none', fontWeight: 600 }}>
              + 신규 바코드 등록
            </a>
            <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 6 }}>아래에 품명을 직접 입력할 수도 있습니다.</div>
          </div>
        ) : (
          <div ref={barcodeRef} style={{ position: 'relative', marginBottom: 12 }}>
            {selectedBarcode ? (
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <div style={{ flex: 1, padding: '8px 10px', background: '#ede9fe', borderRadius: 8, fontSize: 12, color: '#7c3aed', fontWeight: 500 }}>
                  ✅ {selectedBarcode.바코드} — {selectedBarcode.제품명}{selectedBarcode.옵션 ? ' / ' + selectedBarcode.옵션 : ''}
                </div>
                <button onClick={() => { setSelectedBarcode(null); setBarcodeQuery(''); }}
                  style={{ padding: '6px 10px', background: '#f3f4f6', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12, color: '#6b7280' }}>변경</button>
              </div>
            ) : (
              <>
                <input value={barcodeQuery}
                  onChange={e => { setBarcodeQuery(e.target.value); setBarcodeOpen(true); }}
                  onFocus={() => setBarcodeOpen(true)}
                  placeholder={`바코드·제품명 검색 (${barcodeResults.length}개 중)`}
                  style={inputS} />
                {barcodeOpen && fBarcodes.length > 0 && (
                  <div style={dropS}>
                    {fBarcodes.slice(0, 40).map(b => (
                      <div key={b.바코드} onMouseDown={() => selectBarcode(b)}
                        style={{ padding: '8px 12px', cursor: 'pointer', borderBottom: '1px solid #f3f4f6' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <div>
                            <div style={{ fontSize: 13, fontWeight: 500 }}>{b.제품명}{b.옵션 ? ` / ${b.옵션}` : ''}</div>
                            <div style={{ fontSize: 11, color: '#9ca3af', fontFamily: 'monospace' }}>{b.바코드}</div>
                          </div>
                          <span style={{ fontSize: 11, color: '#7c3aed', flexShrink: 0, marginLeft: 8 }}>{b.업체명}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* 품명 */}
        <label style={lbl}>품명 *</label>
        <input value={form.item_name} onChange={e => setForm(f => ({ ...f, item_name: e.target.value }))}
          placeholder="예) 타원 백팩" style={{ ...inputS, marginBottom: 12 }} />

        {/* 옵션 */}
        <label style={lbl}>옵션 (색상·사이즈 등)</label>
        <input value={form.option_text} onChange={e => setForm(f => ({ ...f, option_text: e.target.value }))}
          placeholder="예) 블랙, L" style={{ ...inputS, marginBottom: 12 }} />

        {/* 수량 + 단가 */}
        <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
          <div style={{ flex: 1 }}>
            <label style={lbl}>장끼 수량 *</label>
            <input type="number" inputMode="numeric" min={1} value={form.janggi_qty}
              onChange={e => setForm(f => ({ ...f, janggi_qty: Number(e.target.value) }))}
              style={{ ...inputS, fontSize: 18, fontWeight: 700, textAlign: 'center' }} />
          </div>
          <div style={{ flex: 1 }}>
            <label style={lbl}>단가 (선택)</label>
            <input type="number" inputMode="numeric" min={0} value={form.unit_price}
              onChange={e => setForm(f => ({ ...f, unit_price: e.target.value }))}
              placeholder="0" style={{ ...inputS, textAlign: 'center' }} />
          </div>
        </div>

        {/* 버튼 */}
        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={onClose}
            style={{ flex: 1, padding: 13, border: '1px solid #e5e7f0', background: '#fff', borderRadius: 10, fontSize: 15, fontWeight: 600, cursor: 'pointer', color: '#6b7280' }}>
            취소
          </button>
          <button onClick={handleAdd} disabled={adding || !form.item_name.trim()}
            style={{ flex: 2, padding: 13, border: 'none', background: (adding || !form.item_name.trim()) ? '#9ca3af' : '#4361ee', color: '#fff', borderRadius: 10, fontSize: 15, fontWeight: 700, cursor: (adding || !form.item_name.trim()) ? 'not-allowed' : 'pointer' }}>
            {adding ? '추가 중…' : '추가'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────
// 메인 페이지
// ─────────────────────────────────────

export default function InboundWorkPage() {
  const { id } = useParams<{ id: string }>();
  const [token, setToken] = useState('');
  const [batch, setBatch] = useState<InboundBatch | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [closing, setClosing] = useState(false);
  const [closeMsg, setCloseMsg] = useState('');

  // 작업자 이름 (로그인 없이 접근하는 경우)
  const [workerName, setWorkerName] = useState('');
  const [nameInput, setNameInput] = useState('');
  const [showNameEdit, setShowNameEdit] = useState(false);

  // OCR
  const [ocrLoading, setOcrLoading] = useState(false);
  const [ocrMsg, setOcrMsg] = useState('');

  // 수동 추가 모달
  const [showAddModal, setShowAddModal] = useState(false);

  const reload = useCallback(async (tok: string) => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await getInboundBatch(tok, id);
      setBatch(data);
    } catch {
      setError('입고 정보를 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    const tok = localStorage.getItem('token') || '';
    const savedName = localStorage.getItem('inbound_worker_name') || '';
    setToken(tok);
    setWorkerName(savedName);
    setNameInput(savedName);
    reload(tok);  // 토큰 없어도 로드 가능
  }, [reload]);

  async function handleOcr(file: File) {
    if (!batch) return;
    setOcrLoading(true);
    setOcrMsg('');
    try {
      const res = await runInboundOcr(token, batch.id, file);
      await reload(token);
      setOcrMsg(`✅ OCR 완료: ${res.item_count}개 품목 (자동매칭 ${res.matched_count}개)`);
    } catch (e) {
      setOcrMsg('❌ ' + (e instanceof Error ? e.message : 'OCR 실패'));
    } finally {
      setOcrLoading(false);
    }
  }

  async function handleClose(closeType: 'am' | 'pm') {
    if (!batch) return;
    setClosing(true);
    setCloseMsg('');
    try {
      const res = await closeInboundBatch(token, batch.id, closeType);
      if (!res.ok && res.warning) {
        setCloseMsg('⚠️ ' + res.warning);
      } else {
        await reload(token);
        if (closeType === 'pm' && res.formula_str) {
          setCloseMsg(`✅ ${res.status_label || '완료'}\n${res.formula_str}`);
        } else {
          setCloseMsg('✅ ' + (res.message || res.status_label || '완료'));
        }
      }
    } catch (e) {
      setCloseMsg('오류: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setClosing(false);
    }
  }


  // ── 렌더 ──

  if (error) {
    return (
      <div style={{ minHeight: '100vh', background: '#f0f2f8', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
        <div style={{ background: '#fff', borderRadius: 12, padding: 24, textAlign: 'center', maxWidth: 320 }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>📦</div>
          <div style={{ color: '#dc2626', fontSize: 14 }}>{error}</div>
        </div>
      </div>
    );
  }

  const isAdmin = !!token;

  function saveName() {
    const name = nameInput.trim();
    setWorkerName(name);
    localStorage.setItem('inbound_worker_name', name);
    setShowNameEdit(false);
  }

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', background: '#f0f2f8', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center', color: '#6b7280' }}>
          <div style={{ fontSize: 36, marginBottom: 8 }}>📦</div>
          <div>불러오는 중...</div>
        </div>
      </div>
    );
  }

  if (!batch) return null;

  const items = batch.items || [];
  const doneCount = items.filter(i => i.status !== 'pending').length;
  const progress = items.length > 0 ? Math.round((doneCount / items.length) * 100) : 0;
  // AM/PM 버튼 직접 분기

  const statusC = BATCH_STATUS_COLOR[batch.status] || { bg: '#f3f4f6', color: '#6b7280' };

  return (
    <div style={{ minHeight: '100vh', background: '#f0f2f8', fontFamily: "'Noto Sans KR', sans-serif" }}>
      {/* 상단 헤더 */}
      <div style={{
        background: '#1e2140', color: '#fff',
        padding: '14px 16px',
        position: 'sticky', top: 0, zIndex: 100,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700 }}>📦 {batch.vendor}</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)', marginTop: 1 }}>{batch.inbound_date}</div>
          </div>
          <span style={{
            padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600,
            background: statusC.bg, color: statusC.color,
          }}>
            {batch.status_label}
          </span>
        </div>
        {/* 진행률 바 */}
        {items.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'rgba(255,255,255,0.6)', marginBottom: 4 }}>
              <span>확인 완료 {doneCount}/{items.length}</span>
              <span>{progress}%</span>
            </div>
            <div style={{ height: 6, background: 'rgba(255,255,255,0.2)', borderRadius: 3, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${progress}%`, background: progress === 100 ? '#22c55e' : '#4361ee', borderRadius: 3, transition: 'width 0.3s' }} />
            </div>
          </div>
        )}
      </div>

      {/* 이름 배너 (로그인 없이 접근하는 작업자용) */}
      {!isAdmin && (
        <div style={{
          background: workerName ? '#f0fdf4' : '#fffbeb',
          borderBottom: `2px solid ${workerName ? '#86efac' : '#fbbf24'}`,
          padding: '10px 16px',
        }}>
          {!workerName || showNameEdit ? (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: '#a16207', whiteSpace: 'nowrap' }}>👤 이름:</span>
              <input
                value={nameInput}
                onChange={e => setNameInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') saveName(); }}
                placeholder="이름을 입력하세요"
                autoFocus
                style={{
                  flex: 1, padding: '6px 10px', border: '1px solid #fbbf24',
                  borderRadius: 8, fontSize: 14, outline: 'none',
                }}
              />
              <button
                onClick={saveName}
                disabled={!nameInput.trim()}
                style={{
                  padding: '6px 14px', background: nameInput.trim() ? '#4361ee' : '#9ca3af',
                  color: '#fff', border: 'none', borderRadius: 8,
                  fontSize: 13, fontWeight: 700, cursor: nameInput.trim() ? 'pointer' : 'not-allowed',
                  whiteSpace: 'nowrap',
                }}
              >확인</button>
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 13, color: '#15803d' }}>👤 입력자: <strong>{workerName}</strong></span>
              <button
                onClick={() => { setShowNameEdit(true); setNameInput(workerName); }}
                style={{ fontSize: 12, color: '#6b7280', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
              >변경</button>
            </div>
          )}
        </div>
      )}

      {/* 수량 요약 */}
      <div style={{ display: 'flex', gap: 8, padding: '12px 16px', background: '#fff', borderBottom: '1px solid #f3f4f6' }}>
        {[
          { label: '장끼', value: batch.total_janggi_qty, color: '#1d4ed8' },
          { label: '실입고', value: batch.total_actual_qty, color: '#15803d' },
          { label: '미입고', value: batch.total_missing_qty, color: '#dc2626' },
        ].map(s => (
          <div key={s.label} style={{ flex: 1, textAlign: 'center', padding: '8px 4px', background: '#f8f9fc', borderRadius: 8 }}>
            <div style={{ fontSize: 10, color: '#9ca3af' }}>{s.label}</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: s.color }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* 품목 목록 */}
      <div style={{ padding: '12px 16px' }}>
        {items.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2rem 1rem', color: '#9ca3af' }}>
            <div style={{ fontSize: 40, marginBottom: 8 }}>📋</div>
            {batch.status === 'ocr_pending' ? (
              <>
                <div style={{ fontWeight: 600, color: '#374151', fontSize: 14 }}>장끼 OCR 대기 중</div>
                <div style={{ fontSize: 12, marginTop: 6, lineHeight: 1.6, color: '#6b7280' }}>
                  아래 버튼으로 장끼 사진을 찍으면 AI가 품목을 자동으로 읽어드립니다.
                </div>
              </>
            ) : (
              <>
                <div style={{ fontWeight: 600, color: '#374151', fontSize: 14 }}>OCR 결과 품목 없음</div>
                <div style={{ fontSize: 12, marginTop: 6, lineHeight: 1.6 }}>
                  수기 영수증이거나 인식에 실패했을 수 있습니다.<br />
                  다시 촬영하거나 직접 입력해주세요.
                </div>
              </>
            )}

            {/* OCR 메시지 */}
            {ocrMsg && (
              <div style={{
                margin: '12px 0 0', padding: '10px 14px', borderRadius: 8, fontSize: 13,
                background: ocrMsg.startsWith('✅') ? '#dcfce7' : '#fef2f2',
                color: ocrMsg.startsWith('✅') ? '#15803d' : '#dc2626',
                textAlign: 'left',
              }}>
                {ocrMsg}
              </div>
            )}

            {/* 관리자만: OCR + 품목추가 */}
            {isAdmin && (
              <>
                <label style={{
                  display: 'block', marginTop: 16,
                  padding: '13px 24px',
                  background: ocrLoading ? '#9ca3af' : '#a16207',
                  color: '#fff', borderRadius: 10,
                  fontSize: 15, fontWeight: 700,
                  cursor: ocrLoading ? 'not-allowed' : 'pointer',
                  textAlign: 'center',
                }}>
                  {ocrLoading ? (
                    <span>🤖 AI 분석 중… (10~30초)</span>
                  ) : (
                    <span>📷 장끼 사진 촬영 → AI 분석</span>
                  )}
                  <input
                    type="file"
                    accept="image/*"
                    capture="environment"
                    style={{ display: 'none' }}
                    disabled={ocrLoading}
                    onChange={e => {
                      const f = e.target.files?.[0];
                      if (f) handleOcr(f);
                      e.target.value = '';
                    }}
                  />
                </label>
                <button
                  onClick={() => setShowAddModal(true)}
                  style={{
                    marginTop: 10, padding: '10px 24px',
                    background: 'transparent', color: '#4361ee',
                    border: '2px solid #4361ee', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer',
                  }}
                >
                  ➕ 품목 직접 입력
                </button>
              </>
            )}
          </div>
        ) : (
          items.map(item => (
            <ItemCard
              key={item.id}
              item={item}
              token={token}
              workerName={workerName}
              isAdmin={isAdmin}
              onUpdated={() => reload(token)}
              onDelete={isAdmin ? async () => {
                try {
                  await deleteInboundItem(token, item.id);
                  await reload(token);
                } catch (e) {
                  alert('삭제 실패: ' + (e instanceof Error ? e.message : String(e)));
                }
              } : undefined}
            />
          ))
        )}
      </div>

      {/* 관리자 전용: OCR 재분석 + 품목 직접 추가 */}
      {isAdmin && items.length > 0 && (
        <div style={{ padding: '0 16px 4px', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {ocrMsg && (
            <div style={{
              padding: '10px 14px', borderRadius: 8, fontSize: 13,
              background: ocrMsg.startsWith('✅') ? '#dcfce7' : '#fef2f2',
              color: ocrMsg.startsWith('✅') ? '#15803d' : '#dc2626',
            }}>
              {ocrMsg}
            </div>
          )}
          <label style={{
            display: 'block', padding: '10px',
            border: '2px dashed #fbbf24', background: '#fffbeb',
            color: '#a16207', borderRadius: 8,
            fontSize: 14, fontWeight: 600, cursor: ocrLoading ? 'not-allowed' : 'pointer',
            textAlign: 'center',
          }}>
            {ocrLoading ? '🤖 AI 분석 중…' : '🔄 장끼 재분석 (사진 재촬영)'}
            <input
              type="file" accept="image/*" capture="environment"
              style={{ display: 'none' }}
              disabled={ocrLoading}
              onChange={e => { const f = e.target.files?.[0]; if (f) handleOcr(f); e.target.value = ''; }}
            />
          </label>
          <button
            onClick={() => setShowAddModal(true)}
            style={{
              width: '100%', padding: '10px', border: '2px dashed #c7d2fe',
              background: '#eef2ff', color: '#4361ee', borderRadius: 8,
              fontSize: 14, fontWeight: 600, cursor: 'pointer',
            }}
          >
            ➕ 품목 직접 추가
          </button>
        </div>
      )}

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

      {/* ── AM / PM 마감 버튼 (관리자만) ─────────── */}
      {isAdmin && ['confirming', 'inbound_done', 'grading', 'repairing'].includes(batch.status) && (
        <div style={{ padding: '0 16px 32px' }}>
          {closeMsg && (
            <div style={{
              marginBottom: 10, padding: '10px 14px', borderRadius: 8, fontSize: 13,
              whiteSpace: 'pre-line',
              background: closeMsg.startsWith('✅') ? '#dcfce7' : '#fef2f2',
              color: closeMsg.startsWith('✅') ? '#15803d' : '#dc2626',
            }}>
              {closeMsg}
            </div>
          )}

          {/* 오전: confirming 상태만 */}
          {batch.status === 'confirming' && (
            <button
              onClick={() => handleClose('am')}
              disabled={closing}
              style={{
                width: '100%', padding: '15px', marginBottom: 10,
                background: closing ? '#9ca3af' : '#0369a1',
                color: '#fff', border: 'none', borderRadius: 12,
                fontSize: 16, fontWeight: 700, cursor: closing ? 'not-allowed' : 'pointer',
                boxShadow: '0 4px 12px rgba(3,105,161,0.3)',
              }}
            >
              {closing ? '처리 중…' : '☀️ 오전 입고접수 완료'}
            </button>
          )}

          {/* 오후: inbound_done / grading / repairing 상태 */}
          {['inbound_done', 'grading', 'repairing'].includes(batch.status) && (
            <button
              onClick={() => handleClose('pm')}
              disabled={closing}
              style={{
                width: '100%', padding: '15px',
                background: closing ? '#9ca3af' : '#7c3aed',
                color: '#fff', border: 'none', borderRadius: 12,
                fontSize: 16, fontWeight: 700, cursor: closing ? 'not-allowed' : 'pointer',
                boxShadow: '0 4px 12px rgba(124,58,237,0.3)',
              }}
            >
              {closing ? '처리 중…' : '🌆 오후 최종 마감'}
            </button>
          )}
        </div>
      )}

      {/* 완료 상태 */}
      {batch.status === 'done' && (
        <div style={{ padding: '24px 16px 32px', textAlign: 'center', color: '#15803d' }}>
          <div style={{ fontSize: 48 }}>✅</div>
          <div style={{ fontSize: 16, fontWeight: 700, marginTop: 8 }}>최종 완료</div>
          <div style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>
            {batch.closed_by && `${batch.closed_by}이(가) 마감`}
          </div>
        </div>
      )}
    </div>
  );
}
