'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

function getToken() {
  if (typeof window === 'undefined') return '';
  return localStorage.getItem('token') || '';
}

// ──────────────────────────────────────────────────────────────────
// 타입
// ──────────────────────────────────────────────────────────────────

interface OverviewSummary {
  expected_qty: number;
  received_qty: number;
  missing_qty: number;
  pending_qty: number;
  normal_qty: number;
  defect_pending_qty: number;
  repairing_qty: number;
  repaired_good_qty: number;
  unrecoverable_qty: number;
  final_good_qty: number;
  inbound_progress: number;
  processing_progress: number;
}

interface ItemBreakdown {
  normal: number;
  pending: number;
  defect: number;
  repairing: number;
  repaired_good: number;
  unrecoverable: number;
}

interface OverviewItem {
  id: string;
  line_no: number;
  item_name: string | null;
  option_text: string | null;
  janggi_qty: number;
  actual_qty: number;
  missing_qty: number;
  normal_qty_input: number;
  status: string;
  status_label: string;
  matched_barcode: string | null;
  matched_vendor: string | null;
  matched_product: string | null;
  matched_option: string | null;
  breakdown: ItemBreakdown;
  photos: { id: string; url: string }[];
  defect_logs: DefectEntry[];
  repair_logs: RepairEntry[];
  defect_case_id: string | null;
}

interface DefectEntry {
  id: number;
  날짜: string;
  불량명: string | null;
  수량: number;
  비고: string | null;
  처리결과: string | null;
  before_image: string | null;
  after_image: string | null;
}

interface RepairEntry {
  id: number;
  날짜: string;
  작업: string | null;
  불량명: string | null;
  수량: number;
  비용: number;
  비고: string | null;
  before_image: string | null;
  after_image: string | null;
}

interface TimelineEntry {
  type: 'defect' | 'repair';
  date: string | null;
  item_name: string | null;
  detail: string | null;
  qty: number | null;
  result?: string | null;
  id: number;
}

interface BatchInfo {
  id: string;
  vendor: string;
  inbound_date: string;
  status: string;
  status_label: string;
  wholesale: string | null;
  janggi_date: string | null;
  janggi_no: string | null;
  janggi_url: string | null;
  phase: string;
  memo: string | null;
  created_by: string | null;
  closed_by: string | null;
  closed_at: string | null;
}


interface OverviewData {
  batch: BatchInfo;
  summary: OverviewSummary;
  items: OverviewItem[];
  timeline: TimelineEntry[];
  photos: { janggi: string | null };
}

// ──────────────────────────────────────────────────────────────────
// 스타일 상수
// ──────────────────────────────────────────────────────────────────

const C = {
  brand: '#4f46e5', brandLight: '#eef2ff', brandBorder: '#c7d2fe',
  success: '#16a34a', successLight: '#dcfce7',
  danger: '#dc2626', dangerLight: '#fef2f2',
  warning: '#d97706', warningLight: '#fef9c3',
  purple: '#7c3aed', purpleLight: '#ede9fe',
  orange: '#c2410c', orangeLight: '#ffedd5',
  gray: '#6b7280', grayLight: '#f3f4f6',
  text: '#111827', textSub: '#374151', textMuted: '#6b7280',
  bg: '#f5f6fa', card: '#ffffff', border: '#e5e7eb',
};

const ITEM_STATUS_CHIP: Record<string, { bg: string; color: string; label: string }> = {
  pending:       { bg: C.grayLight,    color: C.gray,    label: '미처리' },
  confirmed:     { bg: C.successLight, color: C.success, label: '정상' },
  missing:       { bg: C.dangerLight,  color: C.danger,  label: '미입고' },
  defect:        { bg: C.orangeLight,  color: C.orange,  label: '불량판정중' },
  repair:        { bg: C.warningLight, color: C.warning, label: '수선중' },
  done:          { bg: C.successLight, color: C.success, label: '수선후정상' },
  unrecoverable: { bg: C.dangerLight,  color: C.danger,  label: '회생불가' },
  etc:           { bg: C.purpleLight,  color: C.purple,  label: '기타' },
};

// ──────────────────────────────────────────────────────────────────
// 서브 컴포넌트
// ──────────────────────────────────────────────────────────────────

function Chip({ status }: { status: string }) {
  const s = ITEM_STATUS_CHIP[status] || { bg: C.grayLight, color: C.gray, label: status };
  return (
    <span style={{ padding: '2px 10px', borderRadius: 12, fontSize: 11, fontWeight: 700,
      background: s.bg, color: s.color }}>
      {s.label}
    </span>
  );
}

function ProgressBar({ value, color = C.brand }: { value: number; color?: string }) {
  return (
    <div style={{ height: 8, background: '#e5e7eb', borderRadius: 4, overflow: 'hidden' }}>
      <div style={{ width: `${Math.min(100, Math.max(0, value))}%`, height: '100%',
        background: color, borderRadius: 4, transition: 'width 0.4s' }} />
    </div>
  );
}

function PhotoGrid({ photos, apiBase }: { photos: { id: string; url: string }[]; apiBase: string }) {
  const [lightbox, setLightbox] = useState<string | null>(null);
  if (!photos.length) return null;
  return (
    <>
      {lightbox && (
        <div onClick={() => setLightbox(null)}
          style={{ position: 'fixed', inset: 0, zIndex: 9999, background: 'rgba(0,0,0,0.88)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
          <img src={lightbox} alt="사진" style={{ maxWidth: '95vw', maxHeight: '90vh', objectFit: 'contain', borderRadius: 8 }} onClick={e => e.stopPropagation()} />
        </div>
      )}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
        {photos.map(p => (
          <img key={p.id} src={`${apiBase}${p.url}`} alt="사진"
            onClick={() => setLightbox(`${apiBase}${p.url}`)}
            style={{ width: 72, height: 72, objectFit: 'cover', borderRadius: 8,
              border: `1px solid ${C.border}`, cursor: 'pointer' }} />
        ))}
      </div>
    </>
  );
}

function QtyBadge({ label, value, color = C.text }: { label: string; value: number; color?: string }) {
  return (
    <div style={{ textAlign: 'center', minWidth: 52 }}>
      <div style={{ fontSize: 10, color: C.textMuted }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 700, color }}>{value}</div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// 메인 페이지
// ──────────────────────────────────────────────────────────────────

export default function InboundOverviewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // 정상처리 수량 입력
  const [editNormalQty, setEditNormalQty] = useState<Record<string, string>>({});
  const [savingNormal, setSavingNormal] = useState<Record<string, boolean>>({});

  // 당일 입고처리 완료
  const [closing, setClosing] = useState(false);
  const [closeMsg, setCloseMsg] = useState('');

  // 입고전표 엑셀 다운로드
  const [xlsLoading, setXlsLoading] = useState(false);

  const token = typeof window !== 'undefined' ? localStorage.getItem('token') || '' : '';

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${API_BASE}/inbound/batches/${id}/overview`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.status === 401) { setError('로그인이 필요합니다.'); return; }
      if (res.status === 404) { setError('입고 배치를 찾을 수 없습니다.'); return; }
      if (!res.ok) { setError(`오류가 발생했습니다. (${res.status})`); return; }
      setData(await res.json());
    } catch {
      setError('데이터를 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [id, token]);

  useEffect(() => { load(); }, [load]);

  // 정상처리 수량 저장
  async function saveNormalQty(itemId: string) {
    const v = parseInt(editNormalQty[itemId] ?? '', 10);
    if (isNaN(v) || v < 0) { alert('올바른 수량을 입력하세요.'); return; }
    setSavingNormal(p => ({ ...p, [itemId]: true }));
    try {
      const res = await fetch(`${API_BASE}/inbound/items/${itemId}/normal-qty`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ normal_qty: v }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        alert(err.detail || '저장 실패');
        return;
      }
      await load();
    } finally {
      setSavingNormal(p => ({ ...p, [itemId]: false }));
    }
  }

  // 당일 입고처리 완료
  async function handleDayClose() {
    if (!confirm('당일 입고처리를 완료 처리하시겠습니까?')) return;
    setClosing(true); setCloseMsg('');
    try {
      const res = await fetch(`${API_BASE}/inbound/batches/${id}/close`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ close_type: 'am' }),
      });
      const data = await res.json();
      if (!data.ok && data.warning) {
        setCloseMsg('⚠️ ' + data.warning);
      } else {
        setCloseMsg('✅ ' + (data.message || '입고처리 완료'));
        await load();
      }
    } catch {
      setCloseMsg('❌ 처리 중 오류가 발생했습니다.');
    } finally {
      setClosing(false);
    }
  }

  // 입고전표 엑셀 다운로드
  async function downloadXls() {
    setXlsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/inbound/batches/${id}/export-xls`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) { alert('다운로드 실패'); return; }
      const disposition = res.headers.get('Content-Disposition') || '';
      const match = disposition.match(/filename\*=UTF-8''(.+)/i);
      const filename = match ? decodeURIComponent(match[1]) : '입고전표.xls';
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href = url; a.download = filename; a.click();
      URL.revokeObjectURL(url);
    } catch { alert('다운로드 중 오류가 발생했습니다.'); }
    finally { setXlsLoading(false); }
  }

  // ── 렌더링 ─────────────────────────────────────────────────────

  if (loading) return (
    <div style={{ minHeight: '100vh', background: C.bg, display: 'flex', alignItems: 'center',
      justifyContent: 'center', fontFamily: "'Noto Sans KR', sans-serif" }}>
      <div style={{ textAlign: 'center', color: C.textMuted }}>
        <div style={{ fontSize: 36, marginBottom: 8 }}>📦</div>
        <div>불러오는 중...</div>
      </div>
    </div>
  );

  if (error) return (
    <div style={{ minHeight: '100vh', background: C.bg, display: 'flex', alignItems: 'center',
      justifyContent: 'center', fontFamily: "'Noto Sans KR', sans-serif" }}>
      <div style={{ background: C.card, borderRadius: 12, padding: 24, textAlign: 'center', color: C.danger }}>
        <div style={{ fontSize: 36, marginBottom: 8 }}>⚠️</div>
        <div>{error}</div>
        <button onClick={() => router.back()}
          style={{ marginTop: 16, padding: '8px 20px', background: C.brand, color: '#fff',
            border: 'none', borderRadius: 8, cursor: 'pointer' }}>
          ← 뒤로
        </button>
      </div>
    </div>
  );

  if (!data) return null;

  const { batch, summary, items, timeline } = data;

  // ── 헤더 ────────────────────────────────────────────────────────
  return (
    <div style={{ minHeight: '100vh', background: C.bg, fontFamily: "'Noto Sans KR', sans-serif" }}>

      {/* 헤더 */}
      <div style={{ background: '#1e2140', color: '#fff', padding: '14px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
          <button onClick={() => router.back()}
            style={{ background: 'transparent', border: 'none', color: 'rgba(255,255,255,0.6)',
              cursor: 'pointer', fontSize: 20, padding: 0 }}>
            ←
          </button>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }}>입고 통합현황</div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>📦 {batch.vendor}</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)', marginTop: 2 }}>
              {batch.inbound_date}
              {batch.wholesale && ` · ${batch.wholesale}`}
              {batch.janggi_no && ` · 장끼 ${batch.janggi_no}`}
            </div>
          </div>
          <span style={{ padding: '4px 12px', borderRadius: 16, fontSize: 12, fontWeight: 700,
            background: 'rgba(255,255,255,0.15)', color: '#fff' }}>
            {batch.phase}
          </span>
        </div>
        {/* 액션 버튼 */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
          <button
            onClick={downloadXls}
            disabled={xlsLoading}
            style={{ padding: '6px 14px', background: xlsLoading ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.15)', color: '#fff',
              border: 'none', borderRadius: 8, cursor: xlsLoading ? 'not-allowed' : 'pointer', fontSize: 12 }}>
            {xlsLoading ? '⏳ 생성 중…' : '📥 입고전표 다운로드'}
          </button>
          <button onClick={() => router.push(`/inbound/${id}`)}
            style={{ padding: '6px 14px', background: 'rgba(255,255,255,0.15)', color: '#fff',
              border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 12 }}>
            ✏️ 작업 화면
          </button>
        </div>
      </div>

      <div style={{ padding: '12px 16px', maxWidth: 900, margin: '0 auto' }}>

        {/* 장끼 원본 사진 */}
        {data.photos.janggi && (
          <div style={{ background: C.card, borderRadius: 12, padding: 12, marginBottom: 12,
            border: `1px solid ${C.border}` }}>
            <div style={{ fontSize: 12, color: C.textMuted, marginBottom: 8 }}>📄 장끼 원본</div>
            <img src={`${API_BASE}${data.photos.janggi}`} alt="장끼"
              style={{ maxWidth: '100%', maxHeight: 200, objectFit: 'contain', borderRadius: 8 }} />
          </div>
        )}

        {/* 수량 요약 카드 */}
        <div style={{ background: C.card, borderRadius: 12, padding: 16, marginBottom: 12,
          border: `1px solid ${C.border}` }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12, color: C.text }}>
            수량 요약
          </div>

          {/* 장끼 / 실입고 / 미입고 */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 16, overflowX: 'auto' }}>
            <QtyBadge label="장끼수량" value={summary.expected_qty} color={C.brand} />
            <QtyBadge label="실입고" value={summary.received_qty} color={C.success} />
            <QtyBadge label="미입고" value={summary.missing_qty} color={C.danger} />
          </div>

          {/* 입고 진행률 */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12,
              color: C.textMuted, marginBottom: 4 }}>
              <span>입고 진행률</span>
              <span style={{ fontWeight: 700, color: C.brand }}>{summary.inbound_progress}%</span>
            </div>
            <ProgressBar value={summary.inbound_progress} color={C.brand} />
          </div>

          {/* 처리 진행률 */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12,
              color: C.textMuted, marginBottom: 4 }}>
              <span>양품화 진행률</span>
              <span style={{ fontWeight: 700, color: C.success }}>{summary.processing_progress}%</span>
            </div>
            <ProgressBar value={summary.processing_progress} color={C.success} />
          </div>

          {/* 상태별 수량 */}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {[
              { label: '미처리',      value: summary.pending_qty,      color: C.gray },
              { label: '정상처리',    value: summary.normal_qty,       color: C.success },
              { label: '불량판정중',  value: summary.defect_pending_qty, color: C.orange },
              { label: '수선중',      value: summary.repairing_qty,    color: C.warning },
              { label: '수선후정상',  value: summary.repaired_good_qty, color: C.success },
              { label: '회생불가',    value: summary.unrecoverable_qty, color: C.danger },
            ].map(s => (
              <div key={s.label} style={{ textAlign: 'center', padding: '6px 12px',
                background: C.grayLight, borderRadius: 8, minWidth: 72 }}>
                <div style={{ fontSize: 10, color: C.textMuted }}>{s.label}</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: s.color }}>{s.value}</div>
              </div>
            ))}
          </div>

          <div style={{ marginTop: 12, padding: '8px 12px', background: C.successLight,
            borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 13, color: C.success, fontWeight: 600 }}>최종 정상수량</span>
            <span style={{ fontSize: 22, fontWeight: 800, color: C.success }}>
              {summary.final_good_qty}
            </span>
          </div>

          {/* 당일 입고처리 완료 버튼 */}
          {batch.status === 'confirming' && (
            <div style={{ marginTop: 14 }}>
              {closeMsg && (
                <div style={{
                  marginBottom: 10, padding: '10px 14px', borderRadius: 10, fontSize: 13, fontWeight: 600,
                  background: closeMsg.startsWith('✅') ? C.successLight : C.dangerLight,
                  color: closeMsg.startsWith('✅') ? C.success : (closeMsg.startsWith('⚠️') ? '#92400e' : C.danger),
                  border: `1px solid ${closeMsg.startsWith('✅') ? '#86efac' : closeMsg.startsWith('⚠️') ? '#fde68a' : '#fecaca'}`,
                }}>
                  {closeMsg}
                </div>
              )}
              <button
                onClick={handleDayClose}
                disabled={closing}
                style={{
                  width: '100%', height: 52, borderRadius: 12,
                  background: closing ? '#d1d5db' : '#0369a1',
                  color: '#fff', border: 'none', fontSize: 16, fontWeight: 800,
                  cursor: closing ? 'not-allowed' : 'pointer',
                  boxShadow: closing ? 'none' : '0 4px 16px rgba(3,105,161,0.35)',
                  letterSpacing: '-0.3px',
                }}
              >
                {closing ? '처리 중…' : '✅ 당일 입고처리 완료'}
              </button>
            </div>
          )}

          {batch.status === 'inbound_done' && (
            <div style={{
              marginTop: 14, padding: '10px 14px', borderRadius: 10, fontSize: 13, fontWeight: 600,
              background: '#dbeafe', color: '#1d4ed8', border: '1px solid #93c5fd', textAlign: 'center',
            }}>
              ✅ 입고처리 완료됨
            </div>
          )}

          {batch.status === 'done' && (
            <div style={{
              marginTop: 14, padding: '10px 14px', borderRadius: 10, fontSize: 13, fontWeight: 600,
              background: C.successLight, color: C.success, border: '1px solid #86efac', textAlign: 'center',
            }}>
              🎉 최종 완료
            </div>
          )}
        </div>

        {/* 품목별 표 */}
        <div style={{ background: C.card, borderRadius: 12, marginBottom: 12,
          border: `1px solid ${C.border}`, overflow: 'hidden' }}>
          <div style={{ padding: '12px 16px', borderBottom: `1px solid ${C.border}`,
            fontSize: 13, fontWeight: 700, color: C.text }}>
            품목별 현황
          </div>

          {/* 모바일: 카드형 / 데스크탑: 테이블 */}
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, minWidth: 640 }}>
              <thead>
                <tr style={{ background: C.grayLight }}>
                  {['#', '품명/바코드', '상태', '장끼', '실입고', '미입고',
                    '정상', '불량', '수선중', '수선후', '회생불가', '정상처리 수량 입력', '기록'].map(h => (
                    <th key={h} style={{ padding: '8px 10px', textAlign: 'center', color: C.textMuted,
                      fontWeight: 600, whiteSpace: 'nowrap', borderBottom: `1px solid ${C.border}` }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((item, idx) => {
                  const bd = item.breakdown;
                  const chip = ITEM_STATUS_CHIP[item.status] || { bg: C.grayLight, color: C.gray, label: item.status };
                  const defectCount = item.defect_logs.length;
                  const repairCount = item.repair_logs.length;
                  return (
                    <tr key={item.id} style={{ borderBottom: `1px solid ${C.border}`,
                      background: idx % 2 === 0 ? '#fff' : '#fafafa' }}>
                      <td style={{ padding: '8px 10px', textAlign: 'center', color: C.textMuted }}>{item.line_no}</td>
                      <td style={{ padding: '8px 10px', minWidth: 140 }}>
                        <div style={{ fontWeight: 600, color: C.text }}>{item.item_name || '(품명 없음)'}</div>
                        {item.option_text && <div style={{ color: C.textMuted, fontSize: 11 }}>{item.option_text}</div>}
                        {item.matched_product && (
                          <div style={{ color: C.purple, fontSize: 11, marginTop: 2 }}>
                            {item.matched_vendor} · {item.matched_product}
                          </div>
                        )}
                        {item.matched_barcode && (
                          <div style={{ color: C.textMuted, fontSize: 10, fontFamily: 'monospace' }}>
                            {item.matched_barcode}
                          </div>
                        )}
                        {item.photos.length > 0 && (
                          <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
                            {item.photos.slice(0, 3).map(p => (
                              <img key={p.id} src={`${API_BASE}${p.url}`} alt=""
                                style={{ width: 36, height: 36, objectFit: 'cover', borderRadius: 4 }} />
                            ))}
                          </div>
                        )}
                      </td>
                      <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                        <span style={{ padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600,
                          background: chip.bg, color: chip.color }}>
                          {chip.label}
                        </span>
                      </td>
                      {[item.janggi_qty, item.actual_qty, item.missing_qty,
                        bd.normal, bd.defect, bd.repairing, bd.repaired_good, bd.unrecoverable
                      ].map((v, i) => (
                        <td key={i} style={{ padding: '8px 10px', textAlign: 'center',
                          fontWeight: v > 0 ? 600 : 400, color: v > 0 ? C.text : C.textMuted }}>
                          {v}
                        </td>
                      ))}
                      {/* 정상처리 수량 입력 */}
                      <td style={{ padding: '6px 10px', textAlign: 'center' }}>
                        <div style={{ display: 'flex', gap: 4, justifyContent: 'center', alignItems: 'center' }}>
                          <input type="number" min="0" max={item.actual_qty}
                            value={editNormalQty[item.id] ?? item.normal_qty_input ?? ''}
                            onChange={e => setEditNormalQty(p => ({ ...p, [item.id]: e.target.value }))}
                            style={{ width: 52, padding: '4px 6px', border: `1px solid ${C.border}`,
                              borderRadius: 6, fontSize: 13, textAlign: 'center' }} />
                          <button onClick={() => saveNormalQty(item.id)}
                            disabled={savingNormal[item.id]}
                            style={{ padding: '4px 8px', background: C.brand, color: '#fff', border: 'none',
                              borderRadius: 6, cursor: 'pointer', fontSize: 11 }}>
                            {savingNormal[item.id] ? '…' : '저장'}
                          </button>
                        </div>
                      </td>
                      {/* 불량·수선 기록 바로가기 */}
                      <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                        <div style={{ display: 'flex', gap: 4, justifyContent: 'center', flexDirection: 'column', alignItems: 'center' }}>
                          {defectCount > 0 && (
                            <a href={`/defect-log?item=${item.id}`}
                              style={{ fontSize: 11, color: C.orange, textDecoration: 'none' }}>
                              불량 {defectCount}건
                            </a>
                          )}
                          {repairCount > 0 && (
                            <a href={`/repair-log?item=${item.id}`}
                              style={{ fontSize: 11, color: C.warning, textDecoration: 'none' }}>
                              수선 {repairCount}건
                            </a>
                          )}
                          {defectCount === 0 && repairCount === 0 && (
                            <span style={{ color: C.textMuted, fontSize: 11 }}>-</span>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* 처리 이력 */}
        {timeline.length > 0 && (
          <div style={{ background: C.card, borderRadius: 12, marginBottom: 12,
            border: `1px solid ${C.border}` }}>
            <div style={{ padding: '12px 16px', borderBottom: `1px solid ${C.border}`,
              fontSize: 13, fontWeight: 700, color: C.text }}>
              처리 이력
            </div>
            <div style={{ padding: '8px 0' }}>
              {timeline.map((ev, i) => (
                <div key={i} style={{ padding: '8px 16px', borderBottom: i < timeline.length - 1 ? `1px solid ${C.border}` : 'none',
                  display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                  <span style={{ fontSize: 16 }}>{ev.type === 'defect' ? '🔴' : '🔧'}</span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: C.text }}>
                      {ev.type === 'defect' ? '불량' : '수선'} — {ev.item_name}
                    </div>
                    <div style={{ fontSize: 11, color: C.textMuted }}>
                      {ev.detail}{ev.qty ? ` (${ev.qty}개)` : ''}{ev.result ? ` · ${ev.result}` : ''}
                    </div>
                  </div>
                  <span style={{ fontSize: 11, color: C.textMuted, whiteSpace: 'nowrap' }}>{ev.date}</span>
                </div>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
