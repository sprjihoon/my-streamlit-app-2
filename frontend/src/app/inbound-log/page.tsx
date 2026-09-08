'use client';

import { useEffect, useState, useCallback } from 'react';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import { Alert } from '@/components/Alert';
import {
  listInboundBatches,
  createInboundBatch,
  getInboundBatch,
  runInboundOcr,
  updateInboundItem,
  closeInboundBatch,
  deleteInboundBatch,
  listInboundVendors,
  downloadInboundBarcodePdf,
  InboundBatch,
  InboundItem,
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

function ItemRow({ item, token, onUpdated }: { item: InboundItem; token: string; onUpdated: () => void }) {
  const [actualQty, setActualQty] = useState(item.actual_qty);
  const [missingQty, setMissingQty] = useState(item.missing_qty);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      const newStatus = actualQty > 0 ? 'confirmed' : missingQty > 0 ? 'missing' : 'pending';
      await updateInboundItem(token, item.id, { actual_qty: actualQty, missing_qty: missingQty, status: newStatus });
      onUpdated();
    } catch {
      alert('저장 실패');
    } finally {
      setSaving(false);
    }
  }

  const tdStyle: React.CSSProperties = { padding: '0.55rem 0.75rem', fontSize: '0.82rem', verticalAlign: 'middle', borderBottom: '1px solid #f3f4f6' };

  return (
    <tr style={{ background: '#fff' }}>
      <td style={{ ...tdStyle, color: '#9ca3af', textAlign: 'center' }}>{item.line_no}</td>
      <td style={tdStyle}>
        <div style={{ fontWeight: 500 }}>{item.item_name || '-'}</div>
        {item.option_text && <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{item.option_text}</div>}
      </td>
      <td style={{ ...tdStyle, textAlign: 'center', fontWeight: 600, color: '#1d4ed8' }}>{item.janggi_qty}</td>
      <td style={tdStyle}>
        {item.matched_product ? (
          <div style={{ fontSize: '0.78rem' }}>
            <div style={{ color: '#7c3aed', fontWeight: 600 }}>{item.matched_vendor}</div>
            <div>{item.matched_product}</div>
            {item.matched_option && <div style={{ color: 'var(--text-secondary)' }}>{item.matched_option}</div>}
            <div style={{ color: '#9ca3af', fontFamily: 'monospace' }}>{item.matched_barcode}</div>
          </div>
        ) : (
          <span style={{ fontSize: '0.78rem', color: '#dc2626' }}>미매칭</span>
        )}
      </td>
      <td style={{ ...tdStyle, textAlign: 'center' }}>
        <input
          type="number" min={0} value={actualQty}
          onChange={e => setActualQty(Number(e.target.value))}
          style={{ width: 56, ...inputStyle, textAlign: 'center', padding: '0.25rem 0.3rem' }}
        />
      </td>
      <td style={{ ...tdStyle, textAlign: 'center' }}>
        <input
          type="number" min={0} value={missingQty}
          onChange={e => setMissingQty(Number(e.target.value))}
          style={{ width: 56, ...inputStyle, textAlign: 'center', padding: '0.25rem 0.3rem' }}
        />
      </td>
      <td style={{ ...tdStyle, textAlign: 'center' }}>
        <StatusBadge status={item.status} label={item.status_label} map={ITEM_STATUS_COLOR} />
      </td>
      <td style={{ ...tdStyle, textAlign: 'center' }}>
        <button onClick={save} disabled={saving} style={btn('#4361ee')}>
          {saving ? '…' : '저장'}
        </button>
      </td>
    </tr>
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
        body: JSON.stringify({ expires_days: 14, allow_excel: false }),
      });
      const data = await res.json();
      setShareLink(data.link);
    } catch (e: unknown) {
      alert('공유 링크 생성 실패: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setShareLoading(false);
    }
  }

  async function handleClose() {
    setCloseLoading(true); setWarning('');
    try {
      const res = await closeInboundBatch(token, batch.id);
      if (!res.ok && res.warning) {
        setWarning(res.warning);
      } else {
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
  const canClose = ['confirming', 'inbound_done', 'grading', 'repairing'].includes(batch.status);
  const closeLabel: Record<string, string> = {
    confirming: '입고접수 완료',
    inbound_done: '양품화 시작',
    grading: '최종 마감',
    repairing: '최종 마감',
  };

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

      {/* 품목 테이블 */}
      {items.length > 0 ? (
        <div style={{ overflowX: 'auto', marginBottom: '1rem' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
            <thead>
              <tr style={{ background: '#f8f9fc' }}>
                {['No', '품명/옵션', '장끼수량', '매칭 상품', '실입고', '미입고', '상태', ''].map(h => (
                  <th key={h} style={{ padding: '0.6rem 0.75rem', fontSize: '0.75rem', color: 'var(--text-secondary)', fontWeight: 600, textAlign: h === '품명/옵션' || h === '매칭 상품' ? 'left' : 'center', borderBottom: '1px solid var(--border)', whiteSpace: 'nowrap' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.map(item => (
                <ItemRow key={item.id} item={item} token={token} onUpdated={reload} />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--text-muted)', fontSize: '0.875rem', background: '#f8f9fc', borderRadius: 8, marginBottom: '1rem' }}>
          장끼 OCR을 실행하면 품목이 표시됩니다.
        </div>
      )}

      {/* 공유 링크 표시 */}
      {shareLink && (
        <div style={{ marginBottom: '0.75rem', padding: '0.75rem 1rem', background: '#f0fff4', border: '1px solid #bbf7d0', borderRadius: 6, fontSize: '0.85rem' }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>🔗 화주사 공유 링크 (14일 유효)</div>
          <div style={{ wordBreak: 'break-all', color: '#4361ee' }}>{shareLink}</div>
          <button onClick={() => { navigator.clipboard.writeText(shareLink); }} style={{ marginTop: 6, fontSize: '0.78rem', ...btnOutline }}>복사</button>
        </div>
      )}

      {/* PDF + 공유 버튼 */}
      <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', marginBottom: '0.75rem' }}>
        <button onClick={handlePdf} disabled={pdfLoading} style={{ ...btn('#0f766e'), opacity: pdfLoading ? 0.5 : 1 }}>
          {pdfLoading ? '생성 중…' : '📄 바코드 PDF'}
        </button>
        <button onClick={handleShare} disabled={shareLoading} style={{ ...btn('#7c3aed'), opacity: shareLoading ? 0.5 : 1 }}>
          {shareLoading ? '생성 중…' : '🔗 화주사 공유 링크'}
        </button>
      </div>

      {/* 마감 버튼 */}
      {canClose && (
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button
            onClick={handleClose}
            disabled={closeLoading}
            style={{ ...btn('var(--color-brand)'), opacity: closeLoading ? 0.5 : 1 }}
          >
            {closeLoading ? '처리 중…' : (closeLabel[batch.status] || '마감')}
          </button>
        </div>
      )}
    </Modal>
  );
}

// ─────────────────────────────────────
// 신규 입고 등록 모달
// ─────────────────────────────────────

function CreateBatchModal({ token, onClose, onCreated }: {
  token: string; onClose: () => void; onCreated: (batch: InboundBatch) => void;
}) {
  const [vendor, setVendor] = useState('');
  const [inboundDate, setInboundDate] = useState(todayStr());
  const [memo, setMemo] = useState('');
  const [vendors, setVendors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    listInboundVendors(token).then(r => setVendors(r.vendors)).catch(() => {});
  }, [token]);

  async function handleCreate() {
    if (!vendor.trim()) { alert('화주사를 입력해주세요.'); return; }
    setSaving(true);
    try {
      const res = await createInboundBatch(token, { vendor: vendor.trim(), inbound_date: inboundDate, memo: memo.trim() || undefined });
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
          <input
            list="vendor-list"
            value={vendor}
            onChange={e => setVendor(e.target.value)}
            placeholder="예: 틸리언"
            style={{ ...inputStyle, width: '100%' }}
          />
          <datalist id="vendor-list">
            {vendors.map(v => <option key={v} value={v} />)}
          </datalist>
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

  const [filterVendor, setFilterVendor] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo] = useState('');

  useEffect(() => { setToken(localStorage.getItem('token') || ''); }, []);

  const load = useCallback(async (tok: string) => {
    if (!tok) return;
    setLoading(true);
    try {
      const res = await listInboundBatches(tok, {
        vendor: filterVendor || undefined,
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
  }, [filterVendor, filterStatus, filterDateFrom, filterDateTo]);

  useEffect(() => { if (token) load(token); }, [token, load]);

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
          <div>
            <label style={labelStyle}>화주사</label>
            <input value={filterVendor} onChange={e => setFilterVendor(e.target.value)} placeholder="전체" style={{ ...inputStyle, width: 120 }} />
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
            onClick={() => { setFilterVendor(''); setFilterStatus(''); setFilterDateFrom(''); setFilterDateTo(''); }}
            style={btnOutline}
          >
            초기화
          </button>
        </div>
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
                      <button
                        onClick={() => handleDelete(b.id)}
                        style={{ background: 'none', border: '1px solid #fca5a5', borderRadius: 4, color: '#dc2626', fontSize: '0.78rem', cursor: 'pointer', padding: '0.25rem 0.6rem' }}
                      >
                        삭제
                      </button>
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
          onCreated={batch => { setShowCreate(false); setSelectedBatch(batch); load(token); }}
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
