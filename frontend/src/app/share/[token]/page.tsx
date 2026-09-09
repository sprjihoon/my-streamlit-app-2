'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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

interface ShareItem {
  id: string;
  line_no: number;
  item_name: string | null;
  option_text: string | null;
  janggi_qty: number;
  actual_qty: number;
  missing_qty: number;
  status: string;
  status_label: string;
  matched_barcode: string | null;
  matched_vendor: string | null;
  matched_product: string | null;
  matched_option: string | null;
  breakdown: {
    normal: number; pending: number; defect: number;
    repairing: number; repaired_good: number; unrecoverable: number;
  };
  photos: { id: string; url: string }[];
  defect_logs: { id: number; 날짜: string; 불량명: string | null; 수량: number; 처리결과: string | null; before_image: string | null; after_image: string | null }[];
  repair_logs: { id: number; 날짜: string; 작업: string | null; 불량명: string | null; 수량: number; before_image: string | null; after_image: string | null }[];
}

interface ShareBatch {
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
  closed_at: string | null;
}

interface ShareData {
  batch: ShareBatch;
  summary: OverviewSummary;
  items: ShareItem[];
  timeline: { type: string; date: string | null; item_name: string | null; detail: string | null; qty: number | null; result?: string | null }[];
  photos: { janggi: string | null };
  expires_at: string;
  updated_at: string | null;
  needs_password?: boolean;
}

// ──────────────────────────────────────────────────────────────────
// 색상
// ──────────────────────────────────────────────────────────────────

const C = {
  brand: '#4f46e5', brandLight: '#eef2ff',
  success: '#16a34a', successLight: '#dcfce7',
  danger: '#dc2626', dangerLight: '#fef2f2',
  warning: '#d97706', warningLight: '#fef9c3',
  orange: '#c2410c', orangeLight: '#ffedd5',
  purple: '#7c3aed', purpleLight: '#ede9fe',
  gray: '#6b7280', grayLight: '#f3f4f6',
  text: '#111827', textMuted: '#6b7280',
  border: '#e5e7eb', card: '#ffffff', bg: '#f0f2f8',
};

const ITEM_CHIPS: Record<string, { bg: string; color: string; label: string }> = {
  pending:       { bg: C.grayLight,    color: C.gray,    label: '미처리' },
  confirmed:     { bg: C.successLight, color: C.success, label: '정상' },
  missing:       { bg: C.dangerLight,  color: C.danger,  label: '미입고' },
  defect:        { bg: C.orangeLight,  color: C.orange,  label: '불량판정중' },
  repair:        { bg: C.warningLight, color: C.warning, label: '수선중' },
  done:          { bg: C.successLight, color: C.success, label: '수선후정상' },
  unrecoverable: { bg: C.dangerLight,  color: C.danger,  label: '회생불가' },
};

function ProgressBar({ value, color = C.brand }: { value: number; color?: string }) {
  return (
    <div style={{ height: 8, background: '#e5e7eb', borderRadius: 4, overflow: 'hidden' }}>
      <div style={{ width: `${Math.min(100, Math.max(0, value))}%`, height: '100%',
        background: color, borderRadius: 4 }} />
    </div>
  );
}

function PhotoViewer({ url, onClose }: { url: string; onClose: () => void }) {
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 9999, background: 'rgba(0,0,0,0.88)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
      <img src={url} alt="사진" style={{ maxWidth: '95vw', maxHeight: '90vh', objectFit: 'contain', borderRadius: 8 }}
        onClick={e => e.stopPropagation()} />
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// 메인 페이지
// ──────────────────────────────────────────────────────────────────

export default function SharePage() {
  const { token } = useParams<{ token: string }>();
  const [data, setData] = useState<ShareData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [needsPw, setNeedsPw] = useState(false);
  const [password, setPassword] = useState('');
  const [pwError, setPwError] = useState('');
  const [lightbox, setLightbox] = useState<string | null>(null);

  async function load(pw?: string) {
    setLoading(true);
    setError('');
    setPwError('');
    try {
      const qs = pw ? `?password=${encodeURIComponent(pw)}` : '';
      // 통합현황 엔드포인트 사용 (기존 /inbound/share/{token} 호환 유지)
      const res = await fetch(`${API_BASE}/inbound/share/${token}/overview${qs}`);
      if (res.status === 404) { setError('링크를 찾을 수 없습니다.'); return; }
      if (res.status === 410) {
        const err = await res.json().catch(() => ({}));
        setError(err.detail || '만료되었거나 폐기된 링크입니다.');
        return;
      }
      if (res.status === 403) { setPwError('비밀번호가 틀렸습니다.'); setNeedsPw(true); return; }
      const json = await res.json();
      if (json.needs_password) { setNeedsPw(true); return; }
      setData(json);
      setNeedsPw(false);
    } catch {
      setError('데이터를 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { if (token) load(); }, [token]);

  // ── 비밀번호 화면 ──
  if (needsPw && !data) {
    return (
      <div style={{ minHeight: '100vh', background: C.bg, display: 'flex', alignItems: 'center',
        justifyContent: 'center', fontFamily: "'Noto Sans KR', sans-serif" }}>
        <div style={{ background: C.card, borderRadius: 16, padding: 32, textAlign: 'center',
          maxWidth: 320, boxShadow: '0 4px 20px rgba(0,0,0,0.1)' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>🔒</div>
          <h2 style={{ fontSize: 16, marginBottom: 16 }}>비밀번호를 입력해주세요</h2>
          {pwError && <div style={{ color: C.danger, fontSize: 13, marginBottom: 8 }}>{pwError}</div>}
          <input type="password" value={password}
            onChange={e => setPassword(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && load(password)}
            placeholder="비밀번호"
            style={{ width: '100%', padding: '10px 12px', border: `1px solid ${C.border}`,
              borderRadius: 8, fontSize: 14, marginBottom: 12, boxSizing: 'border-box' }} />
          <button onClick={() => load(password)}
            style={{ width: '100%', padding: 12, background: C.brand, color: '#fff', border: 'none',
              borderRadius: 8, fontSize: 15, fontWeight: 600, cursor: 'pointer' }}>
            확인
          </button>
        </div>
      </div>
    );
  }

  if (loading) return (
    <div style={{ minHeight: '100vh', background: C.bg, display: 'flex', alignItems: 'center',
      justifyContent: 'center', fontFamily: "'Noto Sans KR', sans-serif" }}>
      <div style={{ textAlign: 'center', color: C.textMuted }}>
        <div style={{ fontSize: 36, marginBottom: 8 }}>📦</div><div>불러오는 중...</div>
      </div>
    </div>
  );

  if (error) return (
    <div style={{ minHeight: '100vh', background: C.bg, display: 'flex', alignItems: 'center',
      justifyContent: 'center', fontFamily: "'Noto Sans KR', sans-serif" }}>
      <div style={{ background: C.card, borderRadius: 12, padding: 24, textAlign: 'center', color: C.danger }}>
        <div style={{ fontSize: 40, marginBottom: 12 }}>⚠️</div>
        <div>{error}</div>
      </div>
    </div>
  );

  if (!data) return null;

  const { batch, summary, items, timeline } = data;

  return (
    <div style={{ minHeight: '100vh', background: C.bg, fontFamily: "'Noto Sans KR', sans-serif" }}>
      {lightbox && <PhotoViewer url={lightbox} onClose={() => setLightbox(null)} />}

      {/* 헤더 */}
      <div style={{ background: '#1e2140', color: '#fff', padding: '14px 20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', marginBottom: 2 }}>입고 현황 공유</div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>📦 {batch.vendor}</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)', marginTop: 2 }}>
              {batch.inbound_date}
              {batch.wholesale && ` · 도매처: ${batch.wholesale}`}
              {batch.janggi_no && ` · 장끼: ${batch.janggi_no}`}
            </div>
          </div>
          <span style={{ padding: '4px 12px', borderRadius: 16, fontSize: 12, fontWeight: 600,
            background: 'rgba(255,255,255,0.15)', color: '#fff' }}>
            {batch.phase}
          </span>
        </div>
      </div>

      <div style={{ padding: '12px 16px', maxWidth: 860, margin: '0 auto' }}>

        {/* 장끼 사진 */}
        {data.photos.janggi && (
          <div style={{ background: C.card, borderRadius: 12, padding: 12, marginBottom: 12,
            border: `1px solid ${C.border}` }}>
            <div style={{ fontSize: 12, color: C.textMuted, marginBottom: 6 }}>장끼 원본</div>
            <img src={`${API_BASE}${data.photos.janggi}`} alt="장끼"
              style={{ maxWidth: '100%', maxHeight: 180, objectFit: 'contain', borderRadius: 8 }} />
          </div>
        )}

        {/* 수량 요약 */}
        <div style={{ background: C.card, borderRadius: 12, padding: 16, marginBottom: 12,
          border: `1px solid ${C.border}` }}>
          {/* 장끼/실입고/미입고 */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 14, overflowX: 'auto' }}>
            {[
              { label: '장끼수량', value: summary.expected_qty, color: C.brand },
              { label: '실입고', value: summary.received_qty, color: C.success },
              { label: '미입고', value: summary.missing_qty, color: C.danger },
            ].map(s => (
              <div key={s.label} style={{ flex: 1, minWidth: 64, textAlign: 'center', padding: '8px 4px',
                background: C.grayLight, borderRadius: 8 }}>
                <div style={{ fontSize: 10, color: C.textMuted }}>{s.label}</div>
                <div style={{ fontSize: 20, fontWeight: 700, color: s.color }}>{s.value}</div>
              </div>
            ))}
          </div>

          {/* 양품화 진행률 */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12,
              color: C.textMuted, marginBottom: 4 }}>
              <span>양품화 진행률</span>
              <span style={{ fontWeight: 700, color: C.success }}>{summary.processing_progress}%</span>
            </div>
            <ProgressBar value={summary.processing_progress} color={C.success} />
          </div>

          {/* 상태별 */}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {[
              { label: '미처리', value: summary.pending_qty, color: C.gray },
              { label: '정상', value: summary.normal_qty, color: C.success },
              { label: '불량확인', value: summary.defect_pending_qty, color: C.orange },
              { label: '수선중', value: summary.repairing_qty, color: C.warning },
              { label: '수선후정상', value: summary.repaired_good_qty, color: C.success },
              { label: '회생불가', value: summary.unrecoverable_qty, color: C.danger },
            ].filter(s => s.value > 0).map(s => (
              <div key={s.label} style={{ padding: '5px 10px', background: C.grayLight,
                borderRadius: 8, textAlign: 'center', minWidth: 64 }}>
                <div style={{ fontSize: 10, color: C.textMuted }}>{s.label}</div>
                <div style={{ fontSize: 15, fontWeight: 700, color: s.color }}>{s.value}</div>
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
        </div>

        {/* 품목 목록 */}
        <div style={{ marginBottom: 12 }}>
          {items.map(item => {
            const chip = ITEM_CHIPS[item.status] || { bg: C.grayLight, color: C.gray, label: item.status };
            const defects = item.defect_logs.filter(d => d.before_image || d.after_image);
            const repairs = item.repair_logs.filter(r => r.before_image || r.after_image);
            return (
              <div key={item.id} style={{ background: C.card, borderRadius: 10, marginBottom: 10,
                border: `1px solid ${C.border}`, overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
                <div style={{ padding: '10px 14px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ fontSize: 11, color: C.textMuted }}>#{item.line_no}</span>
                        <span style={{ padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600,
                          background: chip.bg, color: chip.color }}>
                          {chip.label}
                        </span>
                      </div>
                      <div style={{ fontSize: 14, fontWeight: 600, marginTop: 4 }}>
                        {item.item_name || '(품명 없음)'}
                      </div>
                      {item.option_text && (
                        <div style={{ fontSize: 12, color: C.textMuted }}>{item.option_text}</div>
                      )}
                      {item.matched_product && (
                        <div style={{ fontSize: 11, color: C.purple, marginTop: 2 }}>
                          {item.matched_vendor} · {item.matched_product}
                          {item.matched_option && ` · ${item.matched_option}`}
                        </div>
                      )}
                    </div>
                    {/* 수량 배지 */}
                    <div style={{ display: 'flex', gap: 6, flexShrink: 0, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                      {[
                        { l: '장끼', v: item.janggi_qty, c: C.brand },
                        { l: '실입고', v: item.actual_qty, c: C.success },
                        ...(item.missing_qty > 0 ? [{ l: '미입고', v: item.missing_qty, c: C.danger }] : []),
                      ].map(b => (
                        <div key={b.l} style={{ background: C.grayLight, borderRadius: 6, padding: '3px 8px', textAlign: 'center' }}>
                          <div style={{ fontSize: 10, color: C.textMuted }}>{b.l}</div>
                          <div style={{ fontSize: 14, fontWeight: 700, color: b.c }}>{b.v}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* 제품 사진 */}
                {item.photos.length > 0 && (
                  <div style={{ padding: '6px 14px 10px', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {item.photos.map(ph => (
                      <img key={ph.id} src={`${API_BASE}${ph.url}`} alt="제품사진"
                        onClick={() => setLightbox(`${API_BASE}${ph.url}`)}
                        style={{ width: 64, height: 64, objectFit: 'cover', borderRadius: 8,
                          border: `1px solid ${C.border}`, cursor: 'pointer' }} />
                    ))}
                  </div>
                )}

                {/* 불량 내용 */}
                {item.defect_logs.length > 0 && (
                  <div style={{ borderTop: `1px solid ${C.border}`, padding: '8px 14px',
                    background: C.orangeLight }}>
                    <div style={{ fontSize: 11, color: C.orange, fontWeight: 600, marginBottom: 4 }}>
                      🔴 불량 내용
                    </div>
                    {item.defect_logs.map(d => (
                      <div key={d.id} style={{ fontSize: 12, color: C.text, marginBottom: 4 }}>
                        <b>{d.불량명 || '불량'}</b> {d.수량}개
                        {d.처리결과 && <span style={{ color: C.orange }}> · {d.처리결과}</span>}
                        {(d.before_image || d.after_image) && (
                          <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                            {[d.before_image, d.after_image].filter(Boolean).map((img, i) => (
                              <img key={i} src={`${API_BASE}${img}`} alt="불량사진"
                                onClick={() => setLightbox(`${API_BASE}${img}`)}
                                style={{ width: 56, height: 56, objectFit: 'cover', borderRadius: 6, cursor: 'pointer' }} />
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* 수선 내용 */}
                {item.repair_logs.length > 0 && (
                  <div style={{ borderTop: `1px solid ${C.border}`, padding: '8px 14px',
                    background: C.warningLight }}>
                    <div style={{ fontSize: 11, color: C.warning, fontWeight: 600, marginBottom: 4 }}>
                      🔧 수선 진행
                    </div>
                    {item.repair_logs.map(r => (
                      <div key={r.id} style={{ fontSize: 12, color: C.text, marginBottom: 4 }}>
                        <b>{r.작업 || '수선'}</b> {r.수량}개
                        {r.불량명 && <span style={{ color: C.gray }}> · {r.불량명}</span>}
                        {(r.before_image || r.after_image) && (
                          <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                            {[r.before_image, r.after_image].filter(Boolean).map((img, i) => (
                              <img key={i} src={`${API_BASE}${img}`} alt="수선사진"
                                onClick={() => setLightbox(`${API_BASE}${img}`)}
                                style={{ width: 56, height: 56, objectFit: 'cover', borderRadius: 6, cursor: 'pointer' }} />
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* 처리 이력 */}
        {timeline.length > 0 && (
          <div style={{ background: C.card, borderRadius: 12, marginBottom: 12,
            border: `1px solid ${C.border}` }}>
            <div style={{ padding: '10px 14px', borderBottom: `1px solid ${C.border}`,
              fontSize: 13, fontWeight: 700, color: C.text }}>
              처리 이력
            </div>
            {timeline.map((ev, i) => (
              <div key={i} style={{ padding: '8px 14px', borderBottom: i < timeline.length - 1 ? `1px solid ${C.border}` : 'none',
                display: 'flex', alignItems: 'center', gap: 10 }}>
                <span>{ev.type === 'defect' ? '🔴' : '🔧'}</span>
                <div style={{ flex: 1 }}>
                  <span style={{ fontSize: 12, fontWeight: 600 }}>{ev.item_name}</span>
                  <span style={{ fontSize: 12, color: C.textMuted }}> — {ev.detail}</span>
                  {ev.qty && <span style={{ fontSize: 11, color: C.textMuted }}> ({ev.qty}개)</span>}
                </div>
                <span style={{ fontSize: 11, color: C.textMuted }}>{ev.date}</span>
              </div>
            ))}
          </div>
        )}

        {/* 푸터 */}
        <div style={{ padding: '16px', textAlign: 'center', color: C.textMuted, fontSize: 11 }}>
          {batch.closed_at && `완료: ${batch.closed_at.slice(0, 10)} · `}
          링크 만료: {data.expires_at}
          {data.updated_at && ` · 최근 갱신: ${data.updated_at.slice(0, 10)}`}
        </div>
      </div>
    </div>
  );
}
