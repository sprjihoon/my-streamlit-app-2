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

  // 정상수량 = 실수량 - 불량수량합계 (수선건수는 별도)
  const defectQtySum = item.defect_logs.reduce((s, d) => s + (d.수량 || 0), 0);
  const normalQtyDisplay = Math.max(0, item.actual_qty - defectQtySum);

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
        {/* 정상수량 = 실수량 - 불량수량합계 */}
        <td style={{ padding: '0.5rem 0.6rem', textAlign: 'right', fontWeight: 700, color: defectQtySum > 0 ? C.text : C.success }}>
          {defectQtySum > 0 ? normalQtyDisplay : item.actual_qty}
        </td>
        {/* 불량수량합계 */}
        <td style={{ padding: '0.5rem 0.6rem', textAlign: 'right', color: defectQtySum > 0 ? C.danger : C.muted }}>
          {defectQtySum > 0 ? defectQtySum : '-'}
        </td>
        <td style={{ padding: '0.5rem 0.6rem', textAlign: 'right', color: item.missing_qty > 0 ? C.danger : C.muted }}>
          {item.missing_qty > 0 ? item.missing_qty : '-'}
        </td>
        <td style={{ padding: '0.5rem 0.6rem' }}>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {item.photos.length > 0 && chip('#0284c7', '#e0f2fe', `📷${item.photos.length}`, true)}
            {item.defect_logs.length > 0 && chip(C.danger, C.dangerLight, `불량${defectQtySum}개`, true)}
            {item.repair_logs.length > 0 && chip(C.purple, C.purpleLight, `수선${item.repair_logs.length}건`, true)}
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
          <td colSpan={9} style={{ padding: '0.75rem 1rem', borderBottom: `1px solid ${C.border}` }}>
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
// 불량·수선 세부내역 서브모달
// ─────────────────────────────────────────────
function SubLogModal({
  type, allItems, onClose,
}: {
  type: 'defect' | 'repair';
  allItems: ItemDetail[];
  onClose: () => void;
}) {
  const [lightbox, setLightbox] = useState<string | null>(null);

  // 해당 현황에 속한 로그만 (items에서 추출)
  const rows: { itemName: string; barcode: string | null; log: DefectEntry | RepairEntry }[] = [];
  for (const item of allItems) {
    const name = item.matched_product || item.item_name || '-';
    const bc = item.matched_barcode;
    const logs = type === 'defect' ? item.defect_logs : item.repair_logs;
    for (const log of logs) rows.push({ itemName: name, barcode: bc, log });
  }

  const title = type === 'defect' ? '불량 처리 내역' : '수선 처리 내역';
  const accentColor = type === 'defect' ? C.danger : C.purple;
  const lightColor = type === 'defect' ? C.dangerLight : C.purpleLight;

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <>
      {lightbox && <Lightbox url={lightbox} onClose={() => setLightbox(null)} />}
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.6)', zIndex: 2000, backdropFilter: 'blur(2px)' }} />
      <div style={{
        position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)',
        width: 'min(96vw, 780px)', maxHeight: '88vh',
        background: C.card, borderRadius: 14, boxShadow: '0 28px 70px rgba(0,0,0,0.3)',
        zIndex: 2001, display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}>
        {/* 헤더 */}
        <div style={{ background: lightColor, padding: '0.85rem 1.25rem', borderBottom: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
          <div style={{ fontWeight: 700, fontSize: '1rem', color: accentColor }}>{title}</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: '0.82rem', color: accentColor, fontWeight: 600 }}>{rows.length}건</span>
            <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1.3rem', color: C.muted, lineHeight: 1 }}>✕</button>
          </div>
        </div>
        {/* 바디 */}
        <div style={{ overflowY: 'auto', flex: 1, padding: '0.5rem 0' }}>
          {rows.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '3rem', color: C.muted }}>내역 없음</div>
          ) : rows.map(({ itemName, barcode, log }, idx) => {
            const isDefect = type === 'defect';
            const d = log as DefectEntry;
            const r = log as RepairEntry;
            const before = isDefect ? d.before_image : r.before_image;
            const after  = isDefect ? d.after_image  : r.after_image;
            return (
              <div key={idx} style={{ margin: '0.5rem 1rem', background: lightColor, borderRadius: 8, padding: '0.7rem 0.9rem', border: `1px solid ${accentColor}22` }}>
                {/* 상단: 상품명 / 바코드 / 날짜 */}
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ fontWeight: 700, fontSize: '0.9rem', color: C.text }}>{itemName}</span>
                  {barcode && <span style={{ fontSize: '0.72rem', color: C.muted, background: '#f1f5f9', borderRadius: 4, padding: '1px 6px' }}>{barcode}</span>}
                  <span style={{ fontSize: '0.72rem', color: C.muted, marginLeft: 'auto' }}>{log.날짜}</span>
                </div>
                {/* 상세 정보 */}
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', fontSize: '0.82rem', color: C.textSub, marginBottom: 6 }}>
                  {isDefect ? (
                    <>
                      <span>불량: <b style={{ color: accentColor }}>{d.불량명 || '-'}</b></span>
                      <span>수량: <b>{d.수량}</b></span>
                      {d.처리결과 && <span>처리: <b>{d.처리결과}</b></span>}
                      {d.비고 && <span>비고: {d.비고}</span>}
                      {d.작성자 && <span style={{ color: C.muted }}>작성: {d.작성자}</span>}
                    </>
                  ) : (
                    <>
                      <span>작업: <b style={{ color: accentColor }}>{r.작업 || '-'}</b></span>
                      {r.불량명 && <span>불량명: <b>{r.불량명}</b></span>}
                      <span>수량: <b>{r.수량}</b></span>
                      {r.비용 != null && r.비용 > 0 && <span>비용: <b>{r.비용?.toLocaleString()}원</b></span>}
                      {r.비고 && <span>비고: {r.비고}</span>}
                      {r.작성자 && <span style={{ color: C.muted }}>작성: {r.작성자}</span>}
                    </>
                  )}
                </div>
                {/* 사진 */}
                {(before || after) && (
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {before && (
                      <div>
                        <div style={{ fontSize: '0.65rem', color: C.muted, marginBottom: 2 }}>이전</div>
                        <img src={`${IMG_BASE}${before}`} alt="이전" onClick={() => setLightbox(before)}
                          style={{ width: 80, height: 80, objectFit: 'cover', borderRadius: 6, cursor: 'zoom-in', border: `1px solid ${C.border}` }} />
                      </div>
                    )}
                    {after && (
                      <div>
                        <div style={{ fontSize: '0.65rem', color: C.muted, marginBottom: 2 }}>이후</div>
                        <img src={`${IMG_BASE}${after}`} alt="이후" onClick={() => setLightbox(after)}
                          style={{ width: 80, height: 80, objectFit: 'cover', borderRadius: 6, cursor: 'zoom-in', border: `1px solid ${C.border}` }} />
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
        {/* 푸터 */}
        <div style={{ padding: '0.75rem 1.25rem', borderTop: `1px solid ${C.border}`, display: 'flex', justifyContent: 'flex-end', flexShrink: 0 }}>
          <button onClick={onClose} style={{ background: accentColor, color: '#fff', border: 'none', borderRadius: 7, padding: '0.5rem 1.5rem', cursor: 'pointer', fontWeight: 600, fontSize: '0.875rem' }}>닫기</button>
        </div>
      </div>
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
  const [subModal, setSubModal] = useState<'defect' | 'repair' | null>(null);
  const router = useRouter();

  const loadDetail = useCallback(() => {
    setLoading(true);
    apiFetch<DetailData>(`/inbound/vendor-overview/${encodeURIComponent(vendor)}/${encodeURIComponent(date)}`)
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [vendor, date]);

  useEffect(() => { loadDetail(); }, [loadDetail]);

  // ESC 닫기 (서브모달 없을 때만)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape' && !subModal) onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose, subModal]);

  // 해당 현황에 속한 전체 품목
  const allItems = data ? data.batches.flatMap(b => b.items) : [];
  // 불량수량합계: defect_logs.수량 합산 (수선건수와 무관)
  const totalDefectQty = allItems.flatMap(i => i.defect_logs).reduce((s, d) => s + (d.수량 || 0), 0);
  const totalNormalQty = Math.max(0, (data?.summary.total_actual_qty ?? 0) - totalDefectQty);

  return (
    <>
      {lightbox && <Lightbox url={lightbox} onClose={() => setLightbox(null)} />}
      {subModal && (
        <SubLogModal
          type={subModal}
          allItems={allItems}
          onClose={() => setSubModal(null)}
        />
      )}
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
              {/* 요약 바: 정상수량 = 실수량 - 불량수량합계 / 수선건수는 별도 */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(90px, 1fr))', background: C.bg, borderBottom: `1px solid ${C.border}` }}>
                {([
                  { label: '장끼수량', v: data.summary.total_janggi_qty, color: C.text, clickType: null },
                  { label: '실수량',   v: data.summary.total_actual_qty,  color: C.success, clickType: null },
                  { label: '정상수량', v: totalNormalQty, color: totalNormalQty < data.summary.total_actual_qty ? C.text : C.success, clickType: null },
                  { label: '불량수량', v: totalDefectQty, color: totalDefectQty > 0 ? C.danger : C.muted, clickType: totalDefectQty > 0 ? 'defect' : null },
                  { label: '누락',     v: data.summary.total_missing_qty, color: data.summary.total_missing_qty > 0 ? C.danger : C.muted, clickType: null },
                  { label: '입고율',   v: data.summary.total_janggi_qty > 0 ? `${Math.round(data.summary.total_actual_qty/data.summary.total_janggi_qty*100)}%` : '-', color: C.success, clickType: null },
                  { label: '매칭필요', v: data.summary.needs_matching_count, color: data.summary.needs_matching_count > 0 ? C.warn : C.muted, clickType: null },
                  { label: '수선건수', v: data.summary.repair_total, color: data.summary.repair_total > 0 ? C.purple : C.muted, clickType: data.summary.repair_total > 0 ? 'repair' : null },
                ] as { label: string; v: number | string; color: string; clickType: 'defect' | 'repair' | null }[]).map(s => (
                  <div
                    key={s.label}
                    onClick={() => s.clickType && setSubModal(s.clickType)}
                    style={{
                      padding: '0.65rem 0.5rem', textAlign: 'center', borderRight: `1px solid ${C.border}`,
                      cursor: s.clickType ? 'pointer' : 'default',
                      background: s.clickType ? 'rgba(0,0,0,0.02)' : undefined,
                    }}
                    title={s.clickType ? `${s.label} 클릭하여 상세 보기` : undefined}
                  >
                    <div style={{ fontSize: '0.68rem', color: C.muted, marginBottom: 2 }}>
                      {s.label}{s.clickType && <span style={{ marginLeft: 2, fontSize: '0.6rem' }}>▶</span>}
                    </div>
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

                    <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                      {/* 당일 입고처리 완료 */}
                      {batch.status === 'confirming' && (
                        <button
                          onClick={async () => {
                            if (!confirm('당일 입고처리를 완료 처리하시겠습니까?')) return;
                            try {
                              const res = await fetch(`${API_BASE}/inbound/batches/${batch.id}/close`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
                                body: JSON.stringify({ close_type: 'am' }),
                              });
                              const d = await res.json();
                              if (d.ok) { alert('✅ ' + (d.message || '입고처리 완료')); loadDetail(); }
                              else alert('⚠️ ' + (d.warning || '처리 실패'));
                            } catch { alert('오류가 발생했습니다.'); }
                          }}
                          style={{ background: '#0369a1', border: 'none', borderRadius: 5, color: '#fff', fontSize: '0.75rem', cursor: 'pointer', padding: '3px 10px', fontWeight: 600 }}
                        >
                          ✅ 완료
                        </button>
                      )}
                      {/* 입고전표 다운로드 */}
                      <button
                        onClick={async () => {
                          try {
                            const res = await fetch(`${API_BASE}/inbound/batches/${batch.id}/export-xls`, {
                              headers: { Authorization: `Bearer ${getToken()}` },
                            });
                            if (!res.ok) { alert('엑셀 생성 실패'); return; }
                            const blob = await res.blob();
                            const disp = res.headers.get('Content-Disposition') || '';
                            const match = disp.match(/filename\*=UTF-8''(.+)/i) || disp.match(/filename="?([^"]+)"?/i);
                            const name = match ? decodeURIComponent(match[1]) : `입고전표_${batch.id}.xls`;
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a'); a.href = url; a.download = name; a.click();
                            URL.revokeObjectURL(url);
                          } catch { alert('다운로드 중 오류가 발생했습니다.'); }
                        }}
                        style={{ background: 'none', border: `1px solid #16a34a`, borderRadius: 5, color: '#16a34a', fontSize: '0.75rem', cursor: 'pointer', padding: '3px 10px', fontWeight: 600 }}
                      >
                        📥 입고전표
                      </button>
                      <button
                        onClick={() => router.push(`/inbound/${batch.id}`)}
                        style={{ background: 'none', border: `1px solid ${C.primary}`, borderRadius: 5, color: C.primary, fontSize: '0.75rem', cursor: 'pointer', padding: '3px 10px', fontWeight: 600 }}
                      >
                        입고작업
                      </button>
                    </div>
                  </div>

                  {/* 품목 테이블 */}
                  {batch.items.length > 0 ? (
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
                        <thead>
                          <tr style={{ background: '#f1f5f9' }}>
                            {['#', '상품명/옵션', '장끼', '실수량', '정상', '불량', '누락', '사진·이력', ''].map((h, i) => (
                              <th key={i} style={{ padding: '0.4rem 0.6rem', textAlign: i >= 2 && i <= 6 ? 'right' : 'left', color: C.muted, fontWeight: 600, borderBottom: `1px solid ${C.border}`, whiteSpace: 'nowrap', fontSize: '0.75rem' }}>{h}</th>
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
  // 필터 상태 (입고일지와 동일, 도매처 제외)
  const [filterVendor, setFilterVendor] = useState('');
  const [filterAlias, setFilterAlias] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo] = useState('');
  const [vendorOptions, setVendorOptions] = useState<string[]>([]);
  const [aliasGroups, setAliasGroups] = useState<{ canonical: string; aliases: string[] }[]>([]);
  const [modal, setModal] = useState<{ vendor: string; date: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const qs = new URLSearchParams();
      const vendorParam = filterAlias || filterVendor;
      if (vendorParam) qs.set('vendor', vendorParam);
      if (filterDateFrom) qs.set('date_from', filterDateFrom);
      if (filterDateTo) qs.set('date_to', filterDateTo);
      if (filterStatus) qs.set('status', filterStatus);
      const data = await apiFetch<{ items: OverviewListItem[]; total: number }>(`/inbound/vendor-overview?${qs}`);
      setItems(data.items); setTotal(data.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : '불러오기 실패');
    } finally {
      setLoading(false);
    }
  }, [filterVendor, filterAlias, filterStatus, filterDateFrom, filterDateTo]);

  useEffect(() => {
    apiFetch<{ vendors: string[]; wholesales: string[]; alias_groups?: { canonical: string; aliases: string[] }[] }>('/inbound/filter-options')
      .then(d => { setVendorOptions(d.vendors); setAliasGroups(d.alias_groups ?? []); })
      .catch(() => {});
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

      {/* 필터 (입고일지와 동일, 도매처 제외) */}
      <div style={{ background: C.card, padding: '0.85rem 1rem', borderRadius: 8, border: `1px solid ${C.border}`, marginBottom: '1rem' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.6rem', alignItems: 'flex-end' }}>
          {/* 화주사 (업체명) */}
          <div>
            <div style={{ fontSize: '0.72rem', color: C.muted, marginBottom: 3 }}>화주사 (업체명)</div>
            <select
              value={filterVendor}
              onChange={e => { setFilterVendor(e.target.value); setFilterAlias(''); }}
              style={{ border: `1px solid ${C.border}`, borderRadius: 6, padding: '0.4rem 0.6rem', fontSize: '0.85rem', minWidth: 140 }}
            >
              <option value="">전체</option>
              {vendorOptions.map(v => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>

          {/* 화주사 (별칭) */}
          {aliasGroups.length > 0 && (
            <div>
              <div style={{ fontSize: '0.72rem', color: C.muted, marginBottom: 3 }}>
                화주사 (별칭)
                <span style={{ fontSize: '0.65rem', color: C.muted, marginLeft: 4 }}>일지설정 기준</span>
              </div>
              <select
                value={filterAlias}
                onChange={e => { setFilterAlias(e.target.value); setFilterVendor(''); }}
                style={{ border: `1px solid ${C.border}`, borderRadius: 6, padding: '0.4rem 0.6rem', fontSize: '0.85rem', minWidth: 150 }}
              >
                <option value="">전체</option>
                {aliasGroups.map(g => (
                  <option key={g.canonical} value={g.canonical}>{g.canonical}</option>
                ))}
              </select>
            </div>
          )}

          {/* 상태 */}
          <div>
            <div style={{ fontSize: '0.72rem', color: C.muted, marginBottom: 3 }}>상태</div>
            <select
              value={filterStatus}
              onChange={e => setFilterStatus(e.target.value)}
              style={{ border: `1px solid ${C.border}`, borderRadius: 6, padding: '0.4rem 0.6rem', fontSize: '0.85rem', minWidth: 120 }}
            >
              <option value="">전체</option>
              <option value="open">진행중</option>
              <option value="closed">마감</option>
            </select>
          </div>

          {/* 기간 */}
          <div>
            <div style={{ fontSize: '0.72rem', color: C.muted, marginBottom: 3 }}>기간</div>
            <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
              <input type="date" value={filterDateFrom} onChange={e => setFilterDateFrom(e.target.value)}
                style={{ border: `1px solid ${C.border}`, borderRadius: 6, padding: '0.4rem 0.6rem', fontSize: '0.85rem' }} />
              <span style={{ color: C.muted, fontSize: '0.8rem' }}>~</span>
              <input type="date" value={filterDateTo} onChange={e => setFilterDateTo(e.target.value)}
                style={{ border: `1px solid ${C.border}`, borderRadius: 6, padding: '0.4rem 0.6rem', fontSize: '0.85rem' }} />
            </div>
          </div>

          {/* 버튼 */}
          <button onClick={load}
            style={{ background: C.primary, color: '#fff', border: 'none', borderRadius: 6, padding: '0.45rem 1.1rem', fontSize: '0.85rem', cursor: 'pointer', fontWeight: 600, alignSelf: 'flex-end' }}>
            조회
          </button>
          {(filterVendor || filterAlias || filterStatus || filterDateFrom || filterDateTo) && (
            <button
              onClick={() => { setFilterVendor(''); setFilterAlias(''); setFilterStatus(''); setFilterDateFrom(''); setFilterDateTo(''); }}
              style={{ background: 'none', color: C.muted, border: `1px solid ${C.border}`, borderRadius: 6, padding: '0.45rem 0.8rem', fontSize: '0.85rem', cursor: 'pointer', alignSelf: 'flex-end' }}
            >
              초기화
            </button>
          )}
          <span style={{ alignSelf: 'flex-end', marginLeft: 'auto', fontSize: '0.8rem', color: C.muted, paddingBottom: '0.3rem' }}>총 {total}건</span>
        </div>
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
