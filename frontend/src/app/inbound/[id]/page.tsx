'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import {
  getInboundBatch,
  updateInboundItem,
  closeInboundBatch,
  InboundBatch,
  InboundItem,
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
];

// ─────────────────────────────────────
// 품목 카드 컴포넌트
// ─────────────────────────────────────

function ItemCard({ item, token, onUpdated }: {
  item: InboundItem;
  token: string;
  onUpdated: () => void;
}) {
  const [actualQty, setActualQty] = useState(item.actual_qty);
  const [missingQty, setMissingQty] = useState(item.missing_qty);
  const [status, setStatus] = useState(item.status);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [photos, setPhotos] = useState(item.photos || []);
  const [saved, setSaved] = useState(false);

  async function handleSave() {
    setSaving(true);
    setSaved(false);
    try {
      const autoStatus = actualQty > 0 ? 'confirmed' : missingQty > 0 ? 'missing' : status;
      await updateInboundItem(token, item.id, {
        actual_qty: actualQty,
        missing_qty: missingQty,
        status: autoStatus,
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
      await updateInboundItem(token, item.id, { status: newStatus });
      onUpdated();
    } catch {
      alert('상태 변경 실패');
    } finally {
      setSaving(false);
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
        </div>
        <div style={{
          padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600,
          background: (BATCH_STATUS_COLOR[status]?.bg || '#f3f4f6'),
          color: (BATCH_STATUS_COLOR[status]?.color || '#6b7280'),
          whiteSpace: 'nowrap', flexShrink: 0,
        }}>
          {statusInfo?.label || status}
        </div>
      </div>

      {/* 매칭 상품 */}
      {item.matched_product && (
        <div style={{ padding: '8px 14px', background: '#f8f9fc', fontSize: 12, borderBottom: '1px solid #f3f4f6' }}>
          <span style={{ color: '#7c3aed', fontWeight: 600 }}>{item.matched_vendor}</span>
          {' · '}
          <span>{item.matched_product}</span>
          {item.matched_option && <span style={{ color: '#9ca3af' }}> · {item.matched_option}</span>}
          {item.matched_barcode && <span style={{ fontFamily: 'monospace', color: '#9ca3af' }}> ({item.matched_barcode})</span>}
        </div>
      )}
      {!item.matched_product && (
        <div style={{ padding: '6px 14px', background: '#fef2f2', fontSize: 12, color: '#dc2626', borderBottom: '1px solid #f3f4f6' }}>
          ⚠️ 미매칭 — 수동으로 상품을 연결해주세요
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

        {/* 상태 버튼 그룹 */}
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 6 }}>상태 선택</div>
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

        {/* 저장 버튼 */}
        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            width: '100%', padding: '12px', borderRadius: 8,
            background: saving ? '#9ca3af' : '#4361ee',
            color: '#fff', border: 'none', fontSize: 15, fontWeight: 600,
            cursor: saving ? 'not-allowed' : 'pointer',
            marginBottom: 10,
          }}
        >
          {saving ? '저장 중…' : '수량 저장'}
        </button>

        {/* 제품 사진 */}
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

  useEffect(() => {
    const tok = localStorage.getItem('token') || '';
    setToken(tok);
    if (!tok) {
      setError('로그인이 필요합니다. 앱에서 로그인 후 다시 열어주세요.');
      setLoading(false);
      return;
    }
  }, []);

  const reload = useCallback(async (tok: string) => {
    if (!tok || !id) return;
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
    if (token) reload(token);
  }, [token, reload]);

  async function handleClose() {
    if (!batch) return;
    setClosing(true);
    setCloseMsg('');
    try {
      const res = await closeInboundBatch(token, batch.id);
      if (!res.ok && res.warning) {
        setCloseMsg('⚠️ ' + res.warning);
      } else {
        await reload(token);
        setCloseMsg('✅ ' + (res.status_label || '완료'));
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
          <div style={{ fontSize: 40, marginBottom: 12 }}>🔒</div>
          <div style={{ color: '#dc2626', fontSize: 14 }}>{error}</div>
          <a href="/login" style={{ display: 'block', marginTop: 16, color: '#4361ee', fontSize: 14 }}>로그인 페이지로</a>
        </div>
      </div>
    );
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
  const canClose = ['confirming', 'inbound_done', 'grading', 'repairing'].includes(batch.status);
  const closeLabel: Record<string, string> = {
    confirming: '입고접수 완료로 진행',
    inbound_done: '양품화 시작',
    grading: '최종 마감',
    repairing: '최종 마감',
  };

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
          <div style={{ textAlign: 'center', padding: '3rem 1rem', color: '#9ca3af' }}>
            <div style={{ fontSize: 40, marginBottom: 8 }}>📋</div>
            <div>장끼 OCR 후 품목이 표시됩니다.</div>
            <div style={{ fontSize: 12, marginTop: 8 }}>PC에서 입고일지를 열어 OCR을 먼저 실행해주세요.</div>
          </div>
        ) : (
          items.map(item => (
            <ItemCard key={item.id} item={item} token={token} onUpdated={() => reload(token)} />
          ))
        )}
      </div>

      {/* 마감 버튼 */}
      {canClose && (
        <div style={{ padding: '0 16px 32px' }}>
          {closeMsg && (
            <div style={{
              marginBottom: 10, padding: '10px 14px', borderRadius: 8, fontSize: 13,
              background: closeMsg.startsWith('✅') ? '#dcfce7' : '#fef2f2',
              color: closeMsg.startsWith('✅') ? '#15803d' : '#dc2626',
            }}>
              {closeMsg}
            </div>
          )}
          <button
            onClick={handleClose}
            disabled={closing}
            style={{
              width: '100%', padding: '15px',
              background: closing ? '#9ca3af' : '#4361ee',
              color: '#fff', border: 'none', borderRadius: 12,
              fontSize: 16, fontWeight: 700, cursor: closing ? 'not-allowed' : 'pointer',
              boxShadow: '0 4px 12px rgba(67,97,238,0.3)',
            }}
          >
            {closing ? '처리 중…' : (closeLabel[batch.status] || '마감')}
          </button>
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
