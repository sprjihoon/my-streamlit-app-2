'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const IMG_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

function getToken() {
  if (typeof window === 'undefined') return '';
  return localStorage.getItem('token') || '';
}

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || `Error ${res.status}`);
  }
  return res.json();
}

// ─────────────────────────────────────────────
// 타입
// ─────────────────────────────────────────────
interface OverviewListItem {
  vendor: string;
  inbound_date: string;
  batches_count: number;
  wholesales: string[];
  total_janggi_qty: number;
  total_actual_qty: number;
  total_missing_qty: number;
  all_closed: boolean;
  statuses: string[];
  repair_count: number;
}

interface PhotoEntry { id: string; url: string; }

interface DefectEntry {
  id: number; 날짜: string; 불량명: string | null;
  수량: number; 비고: string | null; 처리결과: string | null;
  before_image: string | null; after_image: string | null; 작성자: string | null;
}

interface RepairEntry {
  id: number; 날짜: string; 작업: string | null; 불량명: string | null;
  수량: number; 비용: number | null; 비고: string | null;
  before_image: string | null; after_image: string | null; 작성자: string | null;
}

interface ItemDetail {
  id: string; batch_id: string; line_no: number;
  item_name: string | null; option_text: string | null; unit_price: number | null;
  janggi_qty: number; actual_qty: number; missing_qty: number; status: string;
  matched_barcode: string | null; matched_product: string | null; matched_option: string | null;
  needs_matching: boolean; normal_qty: number; confirmed_by: string | null; memo: string | null;
  photos: PhotoEntry[];
  defect_logs: DefectEntry[];
  repair_logs: RepairEntry[];
}

interface BatchDetail {
  id: string; wholesale: string; status: string; memo: string | null;
  total_janggi_qty: number; total_actual_qty: number; total_missing_qty: number;
  created_by: string | null; janggi_url: string | null; items: ItemDetail[];
}

interface DetailData {
  vendor: string; inbound_date: string;
  summary: {
    batches_count: number; total_janggi_qty: number; total_actual_qty: number;
    total_missing_qty: number; items_count: number;
    needs_matching_count: number; defect_total: number; repair_total: number;
  };
  batches: BatchDetail[];
}

// ─────────────────────────────────────────────
// 스타일 상수
// ─────────────────────────────────────────────
const C = {
  bg: '#f8fafc', card: '#ffffff', border: '#e2e8f0',
  primary: '#4f46e5', primaryLight: '#eef2ff',
  success: '#059669', successLight: '#d1fae5',
  warn: '#d97706', warnLight: '#fef3c7',
  danger: '#dc2626', dangerLight: '#fee2e2',
  purple: '#7c3aed', purpleLight: '#f5f3ff',
  muted: '#64748b', text: '#0f172a', textSub: '#475569',
};

const chip = (color: string, bg: string, text: string, small = false) => (
  <span style={{ background: bg, color, borderRadius: 4, padding: small ? '1px 5px' : '2px 8px', fontSize: small ? '0.68rem' : '0.75rem', fontWeight: 600, whiteSpace: 'nowrap' as const }}>{text}</span>
);

function statusChip(allClosed: boolean) {
  return allClosed ? chip(C.success, C.successLight, '마감완료') : chip(C.warn, C.warnLight, '진행중');
}

function fmtDate(d: string) {
  if (!d) return '';
  const [, m, day] = d.split('-');
  return `${m}월 ${day}일`;
}

// ─────────────────────────────────────────────
// 이미지 라이트박스
// ─────────────────────────────────────────────
function Lightbox({ url, onClose }: { url: string; onClose: () => void }) {
  return (
    <div
      onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
    >
      <img src={`${IMG_BASE}${url}`} alt="" style={{ maxWidth: '90vw', maxHeight: '90vh', borderRadius: 8, objectFit: 'contain' }} onClick={e => e.stopPropagation()} />
      <button onClick={onClose} style={{ position: 'absolute', top: 20, right: 24, background: 'none', border: 'none', color: '#fff', fontSize: '2rem', cursor: 'pointer' }}>✕</button>
    </div>
  );
}

// ─────────────────────────────────────────────
// 품목 행 (사진·불량·수선 인라인 토글)
// ─────────────────────────────────────────────
function ItemRow({ item }: { item: ItemDetail }) {
  const [open, setOpen] = useState(false);
  const [lightbox, setLightbox] = useState<string | null>(null);

  const hasDetail = item.photos.length > 0 || item.defect_logs.length > 0 || item.repair_logs.length > 0;
  const name = item.matched_product || item.item_name || '-';
  const option = item.matched_option || item.option_text || '';

  return (
    <>
      {lightbox && <Lightbox url={lightbox} onClose={() => setLightbox(null)} />}
      <tr
        onClick={() => hasDetail && setOpen(o => !o)}
        style={{ borderBottom: `1px solid ${C.border}`, background: open ? '#fafbff' : C.card, cursor: hasDetail ? 'pointer' : 'default' }}
      >
        <td style={{ padding: '0.5rem 0.6rem', color: C.muted, fontSize: '0.75rem', width: 28 }}>{item.line_no}</td>
        <td style={{ padding: '0.5rem 0.6rem' }}>
          <div style={{ fontWeight: 500, fontSize: '0.85rem', color: C.text }}>{name}</div>
          {option && <div style={{ fontSize: '0.72rem', color: C.muted }}>{option}</div>}
          {item.needs_matching && <span style={{ fontSize: '0.68rem', color: C.warn }}>⚠ 매칭필요</span>}
        </td>
        <td style={{ padding: '0.5rem 0.6rem', textAlign: 'right', fontWeight: 600 }}>{item.janggi_qty}</td>
        <td style={{ padding: '0.5rem 0.6rem', textAlign: 'right', fontWeight: 700, color: C.success }}>{item.actual_qty}</td>
        <td style={{ padding: '0.5rem 0.6rem', textAlign: 'right', color: item.missing_qty > 0 ? C.danger : C.muted }}>
          {item.missing_qty > 0 ? item.missing_qty : '-'}
        </td>
        <td style={{ padding: '0.5rem 0.6rem' }}>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {item.photos.length > 0 && chip('#0284c7', '#e0f2fe', `📷${item.photos.length}`, true)}
            {item.defect_logs.length > 0 && chip(C.danger, C.dangerLight, `불량${item.defect_logs.length}`, true)}
            {item.repair_logs.length > 0 && chip(C.purple, C.purpleLight, `수선${item.repair_logs.length}`, true)}
            {item.confirmed_by && chip(C.muted, '#f1f5f9', item.confirmed_by, true)}
          </div>
        </td>
        <td style={{ padding: '0.5rem 0.6rem', textAlign: 'center', color: C.muted, fontSize: '0.8rem', width: 24 }}>
          {hasDetail ? (open ? '▲' : '▼') : ''}
        </td>
      </tr>

      {/* 상세 펼침 */}
      {open && (
        <tr style={{ background: '#f8fafc' }}>
          <td colSpan={7} style={{ padding: '0.75rem 1rem', borderBottom: `1px solid ${C.border}` }}>
            {/* 품목 사진 */}
            {item.photos.length > 0 && (
              <div style={{ marginBottom: '0.75rem' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: C.muted, marginBottom: 6 }}>📷 품목 사진</div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {item.photos.map(p => (
                    <img key={p.id} src={`${IMG_BASE}${p.url}`} alt="" onClick={() => setLightbox(p.url)}
                      style={{ width: 72, height: 72, objectFit: 'cover', borderRadius: 6, cursor: 'zoom-in', border: `1px solid ${C.border}` }} />
                  ))}
                </div>
              </div>
            )}

            {/* 불량 로그 */}
            {item.defect_logs.length > 0 && (
              <div style={{ marginBottom: '0.75rem' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: C.danger, marginBottom: 6 }}>🔴 불량 이력</div>
                {item.defect_logs.map(d => (
                  <div key={d.id} style={{ background: C.dangerLight, borderRadius: 6, padding: '0.5rem 0.75rem', marginBottom: 4, fontSize: '0.8rem' }}>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                      <span style={{ fontWeight: 600 }}>{d.날짜}</span>
                      {d.불량명 && <span style={{ color: C.danger }}>{d.불량명}</span>}
                      <span>수량 {d.수량}</span>
                      {d.처리결과 && <span style={{ color: C.textSub }}>→ {d.처리결과}</span>}
                      {d.비고 && <span style={{ color: C.muted }}>{d.비고}</span>}
                      {d.작성자 && chip(C.muted, '#f1f5f9', d.작성자, true)}
                    </div>
                    {(d.before_image || d.after_image) && (
                      <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                        {d.before_image && <img src={`${IMG_BASE}${d.before_image}`} alt="불량전" onClick={() => setLightbox(d.before_image!)}
                          style={{ width: 60, height: 60, objectFit: 'cover', borderRadius: 4, cursor: 'zoom-in', border: `1px solid ${C.border}` }} />}
                        {d.after_image && <img src={`${IMG_BASE}${d.after_image}`} alt="불량후" onClick={() => setLightbox(d.after_image!)}
                          style={{ width: 60, height: 60, objectFit: 'cover', borderRadius: 4, cursor: 'zoom-in', border: `1px solid ${C.border}` }} />}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* 수선 로그 */}
            {item.repair_logs.length > 0 && (
              <div>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: C.purple, marginBottom: 6 }}>🔧 수선 이력</div>
                {item.repair_logs.map(r => (
                  <div key={r.id} style={{ background: C.purpleLight, borderRadius: 6, padding: '0.5rem 0.75rem', marginBottom: 4, fontSize: '0.8rem' }}>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                      <span style={{ fontWeight: 600 }}>{r.날짜}</span>
                      {r.작업 && <span style={{ color: C.purple }}>{r.작업}</span>}
                      {r.불량명 && <span>{r.불량명}</span>}
                      <span>수량 {r.수량}</span>
                      {r.비용 != null && r.비용 > 0 && <span style={{ color: C.warn }}>₩{r.비용.toLocaleString()}</span>}
                      {r.비고 && <span style={{ color: C.muted }}>{r.비고}</span>}
                      {r.작성자 && chip(C.muted, '#f1f5f9', r.작성자, true)}
                    </div>
                    {(r.before_image || r.after_image) && (
                      <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                        {r.before_image && <img src={`${IMG_BASE}${r.before_image}`} alt="수선전" onClick={() => setLightbox(r.before_image!)}
                          style={{ width: 60, height: 60, objectFit: 'cover', borderRadius: 4, cursor: 'zoom-in', border: `1px solid ${C.border}` }} />}
                        {r.after_image && <img src={`${IMG_BASE}${r.after_image}`} alt="수선후" onClick={() => setLightbox(r.after_image!)}
                          style={{ width: 60, height: 60, objectFit: 'cover', borderRadius: 4, cursor: 'zoom-in', border: `1px solid ${C.border}` }} />}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

// ─────────────────────────────────────────────
// 팝업 모달 (통합현황 상세)
// ─────────────────────────────────────────────
function OverviewModal({ vendor, date, onClose }: { vendor: string; date: string; onClose: () => void }) {
  const [data, setData] = useState<DetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [lightbox, setLightbox] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    apiFetch<DetailData>(`/inbound/vendor-overview/${encodeURIComponent(vendor)}/${encodeURIComponent(date)}`)
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [vendor, date]);

  // ESC 닫기
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <>
      {lightbox && <Lightbox url={lightbox} onClose={() => setLightbox(null)} />}
      {/* 배경 오버레이 */}
      <div
        onClick={onClose}
        style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.5)', zIndex: 1000, backdropFilter: 'blur(2px)' }}
      />
      {/* 모달 */}
      <div style={{
        position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)',
        width: 'min(96vw, 900px)', maxHeight: '90vh',
        background: C.card, borderRadius: 14, boxShadow: '0 24px 60px rgba(0,0,0,0.25)',
        zIndex: 1001, display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}>
        {/* 모달 헤더 */}
        <div style={{ background: C.primaryLight, padding: '1rem 1.25rem', borderBottom: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexShrink: 0 }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: '1.05rem', color: C.primary }}>{vendor}</div>
            <div style={{ fontSize: '0.82rem', color: C.textSub, marginTop: 2 }}>
              {date} · {data ? `도매처 ${data.summary.batches_count}곳 · 품목 ${data.summary.items_count}종` : '로딩 중...'}
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1.3rem', color: C.muted, lineHeight: 1 }}>✕</button>
        </div>

        {/* 모달 바디 (스크롤) */}
        <div style={{ overflowY: 'auto', flex: 1 }}>
          {loading && <div style={{ textAlign: 'center', padding: '3rem', color: C.muted }}>불러오는 중...</div>}
          {error && <div style={{ padding: '2rem', color: C.danger }}>{error}</div>}

          {data && (
            <>
              {/* 요약 바 */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(100px, 1fr))', background: C.bg, borderBottom: `1px solid ${C.border}` }}>
                {[
                  { label: '장끼수량', v: data.summary.total_janggi_qty, color: C.text },
                  { label: '실수량',   v: data.summary.total_actual_qty,  color: C.success },
                  { label: '누락',     v: data.summary.total_missing_qty, color: data.summary.total_missing_qty > 0 ? C.danger : C.muted },
                  { label: '입고율',   v: data.summary.total_janggi_qty > 0 ? `${Math.round(data.summary.total_actual_qty/data.summary.total_janggi_qty*100)}%` : '-', color: C.success },
                  { label: '매칭필요', v: data.summary.needs_matching_count, color: data.summary.needs_matching_count > 0 ? C.warn : C.muted },
                  { label: '불량건수', v: data.summary.defect_total, color: data.summary.defect_total > 0 ? C.danger : C.muted },
                  { label: '수선건수', v: data.summary.repair_total, color: data.summary.repair_total > 0 ? C.purple : C.muted },
                ].map(s => (
                  <div key={s.label} style={{ padding: '0.65rem 0.5rem', textAlign: 'center', borderRight: `1px solid ${C.border}` }}>
                    <div style={{ fontSize: '0.68rem', color: C.muted, marginBottom: 2 }}>{s.label}</div>
                    <div style={{ fontWeight: 700, fontSize: '1rem', color: s.color }}>{typeof s.v === 'number' ? s.v.toLocaleString() : s.v}</div>
                  </div>
                ))}
              </div>

              {/* 도매처별 섹션 */}
              {data.batches.map(batch => (
                <div key={batch.id} style={{ borderBottom: `1px solid ${C.border}` }}>
                  {/* 도매처 헤더 */}
                  <div style={{ padding: '0.75rem 1rem', background: '#f8fafc', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                    <span style={{ fontWeight: 700, fontSize: '0.95rem', color: C.text }}>{batch.wholesale}</span>
                    {chip(batch.status === 'closed' ? C.success : C.warn,
                          batch.status === 'closed' ? C.successLight : C.warnLight,
                          batch.status === 'closed' ? '마감' : '진행중')}
                    <span style={{ fontSize: '0.78rem', color: C.muted }}>
                      장끼 {batch.total_janggi_qty} / 실수량 {batch.total_actual_qty}
                      {batch.total_missing_qty > 0 && <span style={{ color: C.danger }}> / 누락 {batch.total_missing_qty}</span>}
                    </span>

                    {/* 장끼 사진 */}
                    {batch.janggi_url && (
                      <span
                        onClick={() => setLightbox(batch.janggi_url!)}
                        style={{ display: 'flex', alignItems: 'center', gap: 4, cursor: 'zoom-in', background: '#e0f2fe', borderRadius: 5, padding: '2px 8px', fontSize: '0.75rem', color: '#0284c7', fontWeight: 600 }}
                      >
                        📄 장끼 사진
                        <img src={`${IMG_BASE}${batch.janggi_url}`} alt="" style={{ width: 28, height: 28, objectFit: 'cover', borderRadius: 3, border: `1px solid ${C.border}` }} />
                      </span>
                    )}

                    <button
                      onClick={() => router.push(`/inbound/${batch.id}`)}
                      style={{ marginLeft: 'auto', background: 'none', border: `1px solid ${C.primary}`, borderRadius: 5, color: C.primary, fontSize: '0.75rem', cursor: 'pointer', padding: '3px 10px', fontWeight: 600 }}
                    >
                      입고작업
                    </button>
                  </div>

                  {/* 품목 테이블 */}
                  {batch.items.length > 0 ? (
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
                        <thead>
                          <tr style={{ background: '#f1f5f9' }}>
                            {['#', '상품명/옵션', '장끼', '실수량', '누락', '사진·이력', ''].map((h, i) => (
                              <th key={i} style={{ padding: '0.4rem 0.6rem', textAlign: i >= 2 && i <= 4 ? 'right' : 'left', color: C.muted, fontWeight: 600, borderBottom: `1px solid ${C.border}`, whiteSpace: 'nowrap', fontSize: '0.75rem' }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {batch.items.map(item => <ItemRow key={item.id} item={item} />)}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div style={{ padding: '1rem', color: C.muted, fontSize: '0.82rem', textAlign: 'center' }}>품목 없음</div>
                  )}
                </div>
              ))}
            </>
          )}
        </div>

        {/* 모달 푸터 */}
        <div style={{ padding: '0.75rem 1.25rem', borderTop: `1px solid ${C.border}`, display: 'flex', justifyContent: 'flex-end', flexShrink: 0 }}>
          <button onClick={onClose} style={{ background: C.primary, color: '#fff', border: 'none', borderRadius: 7, padding: '0.5rem 1.5rem', cursor: 'pointer', fontWeight: 600, fontSize: '0.875rem' }}>닫기</button>
        </div>
      </div>
    </>
  );
}

// ─────────────────────────────────────────────
// 메인 페이지
// ─────────────────────────────────────────────
export default function InboundOverviewPage() {
  const [items, setItems] = useState<OverviewListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filterVendor, setFilterVendor] = useState('');
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo] = useState('');
  const [vendorOptions, setVendorOptions] = useState<string[]>([]);
  const [modal, setModal] = useState<{ vendor: string; date: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const qs = new URLSearchParams();
      if (filterVendor) qs.set('vendor', filterVendor);
      if (filterDateFrom) qs.set('date_from', filterDateFrom);
      if (filterDateTo) qs.set('date_to', filterDateTo);
      const data = await apiFetch<{ items: OverviewListItem[]; total: number }>(`/inbound/vendor-overview?${qs}`);
      setItems(data.items); setTotal(data.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : '불러오기 실패');
    } finally {
      setLoading(false);
    }
  }, [filterVendor, filterDateFrom, filterDateTo]);

  useEffect(() => {
    apiFetch<{ vendors: string[] }>('/inbound/filter-options').then(d => setVendorOptions(d.vendors)).catch(() => {});
    load();
  }, [load]);

  return (
    <div style={{ padding: '1.5rem', maxWidth: 1000, margin: '0 auto', background: C.bg, minHeight: '100vh' }}>
      {/* 모달 */}
      {modal && <OverviewModal vendor={modal.vendor} date={modal.date} onClose={() => setModal(null)} />}

      {/* 헤더 */}
      <div style={{ marginBottom: '1.25rem' }}>
        <h1 style={{ fontSize: '1.2rem', fontWeight: 700, color: C.text, margin: 0 }}>통합 현황</h1>
        <p style={{ fontSize: '0.82rem', color: C.muted, marginTop: 3 }}>화주사 × 입고일 단위 · 여러 도매처 일괄 확인</p>
      </div>

      {/* 필터 */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: '1rem', background: C.card, padding: '0.75rem 1rem', borderRadius: 8, border: `1px solid ${C.border}` }}>
        <select value={filterVendor} onChange={e => setFilterVendor(e.target.value)}
          style={{ border: `1px solid ${C.border}`, borderRadius: 6, padding: '0.4rem 0.6rem', fontSize: '0.85rem', minWidth: 140 }}>
          <option value="">전체 화주사</option>
          {vendorOptions.map(v => <option key={v} value={v}>{v}</option>)}
        </select>
        <input type="date" value={filterDateFrom} onChange={e => setFilterDateFrom(e.target.value)}
          style={{ border: `1px solid ${C.border}`, borderRadius: 6, padding: '0.4rem 0.6rem', fontSize: '0.85rem' }} />
        <span style={{ alignSelf: 'center', color: C.muted }}>~</span>
        <input type="date" value={filterDateTo} onChange={e => setFilterDateTo(e.target.value)}
          style={{ border: `1px solid ${C.border}`, borderRadius: 6, padding: '0.4rem 0.6rem', fontSize: '0.85rem' }} />
        <button onClick={load}
          style={{ background: C.primary, color: '#fff', border: 'none', borderRadius: 6, padding: '0.4rem 1rem', fontSize: '0.85rem', cursor: 'pointer', fontWeight: 600 }}>
          조회
        </button>
        {(filterVendor || filterDateFrom || filterDateTo) && (
          <button onClick={() => { setFilterVendor(''); setFilterDateFrom(''); setFilterDateTo(''); }}
            style={{ background: 'none', color: C.muted, border: `1px solid ${C.border}`, borderRadius: 6, padding: '0.4rem 0.8rem', fontSize: '0.85rem', cursor: 'pointer' }}>
            초기화
          </button>
        )}
        <span style={{ alignSelf: 'center', marginLeft: 'auto', fontSize: '0.8rem', color: C.muted }}>총 {total}건</span>
      </div>

      {error && <div style={{ background: C.dangerLight, color: C.danger, padding: '0.75rem 1rem', borderRadius: 8, marginBottom: '1rem', fontSize: '0.85rem' }}>{error}</div>}

      {/* 목록 */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: C.muted }}>불러오는 중...</div>
      ) : items.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: C.muted }}>
          <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>📦</div>
          <div>입고 데이터가 없습니다.</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
          {items.map(item => {
            const missingRate = item.total_janggi_qty > 0
              ? Math.round((item.total_missing_qty / item.total_janggi_qty) * 100) : 0;
            return (
              <div
                key={`${item.vendor}__${item.inbound_date}`}
                onClick={() => setModal({ vendor: item.vendor, date: item.inbound_date })}
                style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 8, padding: '0.85rem 1rem', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', transition: 'box-shadow 0.15s' }}
                onMouseEnter={e => (e.currentTarget.style.boxShadow = '0 2px 12px rgba(79,70,229,0.12)')}
                onMouseLeave={e => (e.currentTarget.style.boxShadow = 'none')}
              >
                {/* 날짜 */}
                <div style={{ minWidth: 80 }}>
                  <div style={{ fontWeight: 700, fontSize: '0.95rem', color: C.text }}>{fmtDate(item.inbound_date)}</div>
                  <div style={{ fontSize: '0.7rem', color: C.muted }}>{item.inbound_date}</div>
                </div>

                {/* 화주사 */}
                <div style={{ minWidth: 110 }}>
                  <div style={{ fontWeight: 600, color: C.primary, fontSize: '0.9rem' }}>{item.vendor}</div>
                  <div style={{ fontSize: '0.7rem', color: C.muted }}>도매처 {item.batches_count}곳</div>
                </div>

                {/* 도매처 태그 */}
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', flex: 1 }}>
                  {item.wholesales.filter(Boolean).map(w => (
                    <span key={w} style={{ background: '#f1f5f9', border: `1px solid ${C.border}`, borderRadius: 4, padding: '1px 7px', fontSize: '0.73rem', color: C.textSub }}>{w}</span>
                  ))}
                </div>

                {/* 수량 */}
                <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '0.66rem', color: C.muted }}>장끼</div>
                    <div style={{ fontWeight: 700, color: C.text }}>{item.total_janggi_qty}</div>
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '0.66rem', color: C.muted }}>실수량</div>
                    <div style={{ fontWeight: 700, color: C.success }}>{item.total_actual_qty}</div>
                  </div>
                  {item.total_missing_qty > 0 && (
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: '0.66rem', color: C.muted }}>누락</div>
                      <div style={{ fontWeight: 700, color: C.danger }}>{item.total_missing_qty}</div>
                    </div>
                  )}
                  {missingRate > 0 && (
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: '0.66rem', color: C.muted }}>누락률</div>
                      <div style={{ fontWeight: 700, color: C.danger, fontSize: '0.88rem' }}>{missingRate}%</div>
                    </div>
                  )}
                </div>

                {/* 수선건수 */}
                {(item.repair_count ?? 0) > 0 && (
                  <div style={{ textAlign: 'center', minWidth: 48 }}>
                    <div style={{ fontSize: '0.66rem', color: C.muted }}>수선</div>
                    <div style={{ fontWeight: 700, color: '#7c3aed', fontSize: '0.95rem' }}>{item.repair_count}</div>
                  </div>
                )}

                {/* 상태 */}
                {statusChip(item.all_closed)}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
