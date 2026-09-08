'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ─────────────────────────────────────
// 타입
// ─────────────────────────────────────

interface ShareBatch {
  id: string;
  vendor: string;
  inbound_date: string;
  status: string;
  status_label: string;
  wholesale: string | null;
  janggi_date: string | null;
  janggi_no: string | null;
  total_janggi_qty: number;
  total_actual_qty: number;
  total_missing_qty: number;
  created_by: string | null;
  closed_at: string | null;
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
  photos: { id: string; url: string }[];
}

interface ShareData {
  batch: ShareBatch;
  items: ShareItem[];
  allow_excel: boolean;
  expires_at: string;
  needs_password?: boolean;
}

// ─────────────────────────────────────
// 상태 색상
// ─────────────────────────────────────

const ITEM_STATUS_COLOR: Record<string, { bg: string; color: string }> = {
  pending:       { bg: '#f3f4f6', color: '#6b7280' },
  confirmed:     { bg: '#dcfce7', color: '#15803d' },
  missing:       { bg: '#fee2e2', color: '#dc2626' },
  defect:        { bg: '#ffedd5', color: '#c2410c' },
  repair:        { bg: '#fef9c3', color: '#a16207' },
  unrecoverable: { bg: '#fecaca', color: '#991b1b' },
  done:          { bg: '#bbf7d0', color: '#166534' },
};

const BATCH_STATUS_COLOR: Record<string, { bg: string; color: string }> = {
  ocr_pending:  { bg: '#f3f4f6', color: '#6b7280' },
  confirming:   { bg: '#fef9c3', color: '#a16207' },
  inbound_done: { bg: '#dbeafe', color: '#1d4ed8' },
  grading:      { bg: '#ede9fe', color: '#7c3aed' },
  repairing:    { bg: '#ffedd5', color: '#c2410c' },
  done:         { bg: '#dcfce7', color: '#15803d' },
  cancelled:    { bg: '#fee2e2', color: '#dc2626' },
};

// ─────────────────────────────────────
// 사진 뷰어
// ─────────────────────────────────────

function PhotoViewer({ url, onClose }: { url: string; onClose: () => void }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 200,
        background: 'rgba(0,0,0,0.85)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        cursor: 'pointer',
      }}
    >
      <img
        src={url}
        alt="제품사진"
        style={{ maxWidth: '95vw', maxHeight: '90vh', objectFit: 'contain', borderRadius: 8 }}
        onClick={e => e.stopPropagation()}
      />
    </div>
  );
}

// ─────────────────────────────────────
// 메인 페이지
// ─────────────────────────────────────

export default function SharePage() {
  const { token } = useParams<{ token: string }>();
  const [data, setData] = useState<ShareData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [needsPw, setNeedsPw] = useState(false);
  const [password, setPassword] = useState('');
  const [lightbox, setLightbox] = useState<string | null>(null);

  async function load(pw?: string) {
    setLoading(true);
    setError('');
    try {
      const qs = pw ? `?password=${encodeURIComponent(pw)}` : '';
      const res = await fetch(`${API_BASE}/inbound/share/${token}${qs}`);
      if (res.status === 404) { setError('링크를 찾을 수 없습니다.'); return; }
      if (res.status === 410) { setError('링크가 만료되었습니다.'); return; }
      if (res.status === 403) { setError('비밀번호가 틀렸습니다.'); return; }
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
  if (needsPw) {
    return (
      <div style={{ minHeight: '100vh', background: '#f0f2f8', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Noto Sans KR', sans-serif" }}>
        <div style={{ background: '#fff', borderRadius: 16, padding: 32, textAlign: 'center', maxWidth: 320, boxShadow: '0 4px 20px rgba(0,0,0,0.1)' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>🔒</div>
          <h2 style={{ fontSize: 16, marginBottom: 16 }}>비밀번호를 입력해주세요</h2>
          {error && <div style={{ color: '#dc2626', fontSize: 13, marginBottom: 8 }}>{error}</div>}
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && load(password)}
            placeholder="비밀번호"
            style={{ width: '100%', padding: '10px 12px', border: '1px solid #e5e7f0', borderRadius: 8, fontSize: 14, marginBottom: 12 }}
          />
          <button
            onClick={() => load(password)}
            style={{ width: '100%', padding: 12, background: '#4361ee', color: '#fff', border: 'none', borderRadius: 8, fontSize: 15, fontWeight: 600, cursor: 'pointer' }}
          >
            확인
          </button>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', background: '#f0f2f8', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Noto Sans KR', sans-serif" }}>
        <div style={{ textAlign: 'center', color: '#6b7280' }}>
          <div style={{ fontSize: 36, marginBottom: 8 }}>📦</div>
          <div>불러오는 중...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ minHeight: '100vh', background: '#f0f2f8', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Noto Sans KR', sans-serif" }}>
        <div style={{ background: '#fff', borderRadius: 12, padding: 24, textAlign: 'center', color: '#dc2626' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>⚠️</div>
          <div>{error}</div>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const { batch, items } = data;
  const batchC = BATCH_STATUS_COLOR[batch.status] || { bg: '#f3f4f6', color: '#6b7280' };

  // 상태별 집계
  const stats: Record<string, number> = {};
  items.forEach(i => { stats[i.status] = (stats[i.status] || 0) + i.actual_qty; });

  return (
    <div style={{ minHeight: '100vh', background: '#f0f2f8', fontFamily: "'Noto Sans KR', sans-serif" }}>
      {/* 사진 라이트박스 */}
      {lightbox && <PhotoViewer url={lightbox} onClose={() => setLightbox(null)} />}

      {/* 헤더 */}
      <div style={{ background: '#1e2140', color: '#fff', padding: '16px 20px' }}>
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
          <span style={{ padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600, background: batchC.bg, color: batchC.color }}>
            {batch.status_label}
          </span>
        </div>
      </div>

      {/* 수량 요약 */}
      <div style={{ display: 'flex', gap: 8, padding: '12px 16px', background: '#fff', borderBottom: '1px solid #f3f4f6' }}>
        {[
          { label: '장끼수량', value: batch.total_janggi_qty, color: '#1d4ed8' },
          { label: '실입고', value: batch.total_actual_qty, color: '#15803d' },
          { label: '미입고', value: batch.total_missing_qty, color: '#dc2626' },
        ].map(s => (
          <div key={s.label} style={{ flex: 1, textAlign: 'center', padding: '8px 4px', background: '#f8f9fc', borderRadius: 8 }}>
            <div style={{ fontSize: 10, color: '#9ca3af' }}>{s.label}</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: s.color }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* 상태별 요약 */}
      <div style={{ padding: '10px 16px', background: '#fff', borderBottom: '1px solid #f3f4f6', display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {Object.entries(ITEM_STATUS_COLOR).map(([status, c]) => {
          const cnt = items.filter(i => i.status === status).length;
          if (cnt === 0) return null;
          return (
            <span key={status} style={{ padding: '3px 10px', borderRadius: 12, fontSize: 12, fontWeight: 600, background: c.bg, color: c.color }}>
              {{ pending: '확인전', confirmed: '정상', missing: '미입고', defect: '불량', repair: '수선대기', unrecoverable: '회생불가', done: '완료' }[status] || status} {cnt}
            </span>
          );
        })}
      </div>

      {/* 품목 목록 */}
      <div style={{ padding: '12px 16px' }}>
        {items.map(item => {
          const ic = ITEM_STATUS_COLOR[item.status] || { bg: '#f3f4f6', color: '#6b7280' };
          return (
            <div key={item.id} style={{
              background: '#fff', borderRadius: 10, marginBottom: 10,
              border: '1px solid #e5e7f0', overflow: 'hidden',
              boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
            }}>
              <div style={{ padding: '10px 14px', borderBottom: item.photos.length > 0 ? '1px solid #f3f4f6' : undefined }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ fontSize: 11, color: '#9ca3af' }}>#{item.line_no}</span>
                    </div>
                    <div style={{ fontSize: 14, fontWeight: 600 }}>{item.item_name || '(품명 없음)'}</div>
                    {item.option_text && <div style={{ fontSize: 12, color: '#6b7280' }}>{item.option_text}</div>}
                    {item.matched_product && (
                      <div style={{ fontSize: 11, color: '#7c3aed', marginTop: 2 }}>
                        {item.matched_vendor} · {item.matched_product}
                        {item.matched_option && ` · ${item.matched_option}`}
                      </div>
                    )}
                    {item.matched_barcode && (
                      <div style={{ fontSize: 10, color: '#9ca3af', fontFamily: 'monospace' }}>{item.matched_barcode}</div>
                    )}
                  </div>
                  <div style={{ flexShrink: 0 }}>
                    <span style={{ padding: '3px 10px', borderRadius: 12, fontSize: 11, fontWeight: 600, background: ic.bg, color: ic.color }}>
                      {item.status_label}
                    </span>
                    <div style={{ display: 'flex', gap: 8, marginTop: 6, fontSize: 11, textAlign: 'center' }}>
                      <div style={{ background: '#f0f4ff', borderRadius: 6, padding: '3px 8px' }}>
                        <span style={{ color: '#9ca3af' }}>장끼</span>{' '}
                        <span style={{ fontWeight: 700, color: '#1d4ed8' }}>{item.janggi_qty}</span>
                      </div>
                      <div style={{ background: '#f0fff4', borderRadius: 6, padding: '3px 8px' }}>
                        <span style={{ color: '#9ca3af' }}>실입고</span>{' '}
                        <span style={{ fontWeight: 700, color: '#15803d' }}>{item.actual_qty}</span>
                      </div>
                      {item.missing_qty > 0 && (
                        <div style={{ background: '#fff0f0', borderRadius: 6, padding: '3px 8px' }}>
                          <span style={{ color: '#9ca3af' }}>미입고</span>{' '}
                          <span style={{ fontWeight: 700, color: '#dc2626' }}>{item.missing_qty}</span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* 제품 사진 */}
              {item.photos.length > 0 && (
                <div style={{ padding: '8px 14px', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {item.photos.map(ph => (
                    <img
                      key={ph.id}
                      src={`${API_BASE}${ph.url}`}
                      alt="제품사진"
                      onClick={() => setLightbox(`${API_BASE}${ph.url}`)}
                      style={{
                        width: 64, height: 64, objectFit: 'cover', borderRadius: 8,
                        border: '1px solid #e5e7f0', cursor: 'pointer',
                      }}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* 푸터 */}
      <div style={{ padding: '16px', textAlign: 'center', color: '#9ca3af', fontSize: 11 }}>
        {batch.created_by && `담당: ${batch.created_by}`}
        {batch.closed_at && ` · 완료: ${batch.closed_at.slice(0, 10)}`}
        <br />링크 만료: {data.expires_at}
      </div>
    </div>
  );
}
