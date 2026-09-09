'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

function getToken() {
  if (typeof window === 'undefined') return '';
  return localStorage.getItem('token') || '';
}

async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers: { Authorization: `Bearer ${getToken()}`, 'Content-Type': 'application/json', ...(opts?.headers || {}) },
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `Error ${res.status}`);
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
}

interface BatchDetail {
  id: string;
  vendor: string;
  inbound_date: string;
  status: string;
  memo: string | null;
  wholesale: string;
  total_janggi_qty: number;
  total_actual_qty: number;
  total_missing_qty: number;
  created_by: string | null;
  closed_by: string | null;
  items: ItemDetail[];
}

interface ItemDetail {
  id: string;
  batch_id: string;
  line_no: number;
  item_name: string | null;
  option_text: string | null;
  unit_price: number | null;
  janggi_qty: number;
  actual_qty: number;
  missing_qty: number;
  status: string;
  matched_barcode: string | null;
  matched_product: string | null;
  matched_option: string | null;
  needs_matching: boolean;
  normal_qty: number;
  confirmed_by: string | null;
  defect_count: number;
  repair_count: number;
}

interface DetailData {
  vendor: string;
  inbound_date: string;
  summary: {
    batches_count: number;
    total_janggi_qty: number;
    total_actual_qty: number;
    total_missing_qty: number;
    items_count: number;
    needs_matching_count: number;
    defect_total: number;
  };
  batches: BatchDetail[];
}

// ─────────────────────────────────────────────
// 스타일 상수
// ─────────────────────────────────────────────
const C = {
  bg: '#f8fafc',
  card: '#ffffff',
  border: '#e2e8f0',
  primary: '#4f46e5',
  primaryLight: '#eef2ff',
  success: '#059669',
  successLight: '#d1fae5',
  warn: '#d97706',
  warnLight: '#fef3c7',
  danger: '#dc2626',
  dangerLight: '#fee2e2',
  muted: '#64748b',
  text: '#0f172a',
  textSub: '#475569',
};

const chip = (color: string, bg: string, text: string) => (
  <span style={{ background: bg, color, borderRadius: 4, padding: '1px 7px', fontSize: '0.72rem', fontWeight: 600 }}>
    {text}
  </span>
);

function statusChip(statuses: string[], allClosed: boolean) {
  if (allClosed) return chip(C.success, C.successLight, '마감완료');
  const hasActive = statuses.some(s => s !== 'closed');
  if (hasActive) return chip(C.warn, C.warnLight, '진행중');
  return chip(C.muted, '#f1f5f9', '대기');
}

function itemStatusChip(status: string) {
  const map: Record<string, [string, string, string]> = {
    confirmed: [C.success, C.successLight, '확인완료'],
    pending: [C.warn, C.warnLight, '미확인'],
    missing: [C.danger, C.dangerLight, '누락'],
    defect: ['#7c3aed', '#f5f3ff', '불량'],
  };
  const [c, bg, label] = map[status] ?? [C.muted, '#f1f5f9', status];
  return chip(c, bg, label);
}

function fmtDate(d: string) {
  if (!d) return '';
  const [y, m, day] = d.split('-');
  return `${m}월 ${day}일`;
}

function numBadge(n: number, color = C.primary) {
  return <span style={{ fontWeight: 700, color }}>{n.toLocaleString()}</span>;
}

// ─────────────────────────────────────────────
// 상세 패널
// ─────────────────────────────────────────────
function DetailPanel({ vendor, date, onClose }: { vendor: string; date: string; onClose: () => void }) {
  const [data, setData] = useState<DetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [openBatch, setOpenBatch] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    setLoading(true);
    apiFetch<DetailData>(`/inbound/vendor-overview/${encodeURIComponent(vendor)}/${encodeURIComponent(date)}`)
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [vendor, date]);

  if (loading) return (
    <div style={{ textAlign: 'center', padding: '3rem', color: C.muted }}>불러오는 중...</div>
  );
  if (error) return (
    <div style={{ padding: '2rem', color: C.danger }}>{error}</div>
  );
  if (!data) return null;

  const { summary, batches } = data;
  const missingRate = summary.total_janggi_qty > 0
    ? Math.round((summary.total_missing_qty / summary.total_janggi_qty) * 100)
    : 0;
  const receiveRate = summary.total_janggi_qty > 0
    ? Math.round((summary.total_actual_qty / summary.total_janggi_qty) * 100)
    : 0;

  return (
    <div style={{ background: C.card, borderRadius: 12, border: `1px solid ${C.border}`, overflow: 'hidden' }}>
      {/* 헤더 */}
      <div style={{ background: C.primaryLight, borderBottom: `1px solid ${C.border}`, padding: '1rem 1.25rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: '1.05rem', color: C.primary }}>{vendor}</div>
          <div style={{ fontSize: '0.85rem', color: C.textSub, marginTop: 2 }}>{date} · 도매처 {summary.batches_count}곳 · 품목 {summary.items_count}종</div>
        </div>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1.2rem', color: C.muted, padding: '0.25rem' }}>✕</button>
      </div>

      {/* 요약 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 1, background: C.border }}>
        {[
          { label: '장끼수량', value: summary.total_janggi_qty, color: C.text },
          { label: '실수량', value: summary.total_actual_qty, color: C.success },
          { label: '누락', value: summary.total_missing_qty, color: C.danger },
          { label: '입고율', value: `${receiveRate}%`, color: receiveRate >= 100 ? C.success : C.warn },
          { label: '누락률', value: `${missingRate}%`, color: missingRate > 0 ? C.danger : C.success },
          { label: '매칭필요', value: summary.needs_matching_count, color: summary.needs_matching_count > 0 ? C.warn : C.success },
          { label: '불량건수', value: summary.defect_total, color: summary.defect_total > 0 ? C.danger : C.success },
        ].map(s => (
          <div key={s.label} style={{ background: C.card, padding: '0.75rem 1rem', textAlign: 'center' }}>
            <div style={{ fontSize: '0.72rem', color: C.muted, marginBottom: 3 }}>{s.label}</div>
            <div style={{ fontWeight: 700, fontSize: '1.15rem', color: s.color }}>{typeof s.value === 'number' ? s.value.toLocaleString() : s.value}</div>
          </div>
        ))}
      </div>

      {/* 도매처별 배치 */}
      <div style={{ padding: '1rem' }}>
        {batches.map(batch => (
          <div key={batch.id} style={{ marginBottom: '0.75rem', border: `1px solid ${C.border}`, borderRadius: 8, overflow: 'hidden' }}>
            {/* 도매처 헤더 */}
            <div
              onClick={() => setOpenBatch(openBatch === batch.id ? null : batch.id)}
              style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.7rem 1rem', background: '#f8fafc', cursor: 'pointer', userSelect: 'none' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontWeight: 600, fontSize: '0.9rem', color: C.text }}>{batch.wholesale}</span>
                <span style={{ fontSize: '0.75rem', color: C.muted }}>품목 {batch.items.length}종</span>
                {chip(batch.status === 'closed' ? C.success : C.warn,
                      batch.status === 'closed' ? C.successLight : C.warnLight,
                      batch.status === 'closed' ? '마감' : '진행중')}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: '0.8rem', color: C.textSub }}>
                  장끼 {batch.total_janggi_qty} / 실수량 {batch.total_actual_qty}
                  {batch.total_missing_qty > 0 && <span style={{ color: C.danger }}> / 누락 {batch.total_missing_qty}</span>}
                </span>
                <button
                  onClick={e => { e.stopPropagation(); router.push(`/inbound/${batch.id}`); }}
                  style={{ background: 'none', border: `1px solid ${C.primary}`, borderRadius: 4, color: C.primary, fontSize: '0.72rem', cursor: 'pointer', padding: '2px 8px', fontWeight: 600 }}
                >
                  입고작업
                </button>
                <span style={{ color: C.muted, fontSize: '0.85rem' }}>{openBatch === batch.id ? '▲' : '▼'}</span>
              </div>
            </div>

            {/* 품목 테이블 */}
            {openBatch === batch.id && (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
                  <thead>
                    <tr style={{ background: '#f1f5f9' }}>
                      {['#', '상품명', '옵션', '장끼', '실수량', '누락', '상태', '불량', '수선', '확인자'].map(h => (
                        <th key={h} style={{ padding: '0.4rem 0.6rem', textAlign: 'left', color: C.muted, fontWeight: 600, borderBottom: `1px solid ${C.border}`, whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {batch.items.map((item, idx) => (
                      <tr key={item.id} style={{ background: idx % 2 === 0 ? C.card : '#fafafa', borderBottom: `1px solid ${C.border}` }}>
                        <td style={{ padding: '0.4rem 0.6rem', color: C.muted }}>{item.line_no}</td>
                        <td style={{ padding: '0.4rem 0.6rem', fontWeight: 500 }}>
                          {item.matched_product || item.item_name || '-'}
                          {item.needs_matching && <span style={{ marginLeft: 4, fontSize: '0.68rem', color: C.warn }}>⚠매칭필요</span>}
                        </td>
                        <td style={{ padding: '0.4rem 0.6rem', color: C.textSub }}>{item.matched_option || item.option_text || '-'}</td>
                        <td style={{ padding: '0.4rem 0.6rem', textAlign: 'right' }}>{item.janggi_qty}</td>
                        <td style={{ padding: '0.4rem 0.6rem', textAlign: 'right', color: C.success, fontWeight: 600 }}>{item.actual_qty}</td>
                        <td style={{ padding: '0.4rem 0.6rem', textAlign: 'right', color: item.missing_qty > 0 ? C.danger : C.muted }}>{item.missing_qty || '-'}</td>
                        <td style={{ padding: '0.4rem 0.6rem' }}>{itemStatusChip(item.status)}</td>
                        <td style={{ padding: '0.4rem 0.6rem', textAlign: 'right', color: item.defect_count > 0 ? C.danger : C.muted }}>{item.defect_count || '-'}</td>
                        <td style={{ padding: '0.4rem 0.6rem', textAlign: 'right', color: item.repair_count > 0 ? '#7c3aed' : C.muted }}>{item.repair_count || '-'}</td>
                        <td style={{ padding: '0.4rem 0.6rem', color: C.muted, fontSize: '0.75rem' }}>{item.confirmed_by || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
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

  // 필터
  const [filterVendor, setFilterVendor] = useState('');
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo] = useState('');
  const [vendorOptions, setVendorOptions] = useState<string[]>([]);

  // 선택된 상세
  const [selected, setSelected] = useState<{ vendor: string; date: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const qs = new URLSearchParams();
      if (filterVendor) qs.set('vendor', filterVendor);
      if (filterDateFrom) qs.set('date_from', filterDateFrom);
      if (filterDateTo) qs.set('date_to', filterDateTo);
      const data = await apiFetch<{ items: OverviewListItem[]; total: number }>(
        `/inbound/vendor-overview?${qs}`
      );
      setItems(data.items);
      setTotal(data.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : '불러오기 실패');
    } finally {
      setLoading(false);
    }
  }, [filterVendor, filterDateFrom, filterDateTo]);

  useEffect(() => {
    // 화주사 목록
    apiFetch<{ vendors: string[]; wholesales: string[] }>('/inbound/filter-options')
      .then(d => setVendorOptions(d.vendors))
      .catch(() => {});
    load();
  }, [load]);

  return (
    <div style={{ padding: '1.5rem', maxWidth: 1100, margin: '0 auto', background: C.bg, minHeight: '100vh' }}>
      {/* 페이지 헤더 */}
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ fontSize: '1.25rem', fontWeight: 700, color: C.text, margin: 0 }}>통합 현황</h1>
        <p style={{ fontSize: '0.85rem', color: C.muted, marginTop: 4 }}>
          화주사 × 입고일 단위 현황 — 여러 도매처 일괄 확인
        </p>
      </div>

      {/* 필터 */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: '1rem', background: C.card, padding: '0.75rem 1rem', borderRadius: 8, border: `1px solid ${C.border}` }}>
        <select
          value={filterVendor}
          onChange={e => setFilterVendor(e.target.value)}
          style={{ border: `1px solid ${C.border}`, borderRadius: 6, padding: '0.4rem 0.6rem', fontSize: '0.85rem', minWidth: 150 }}
        >
          <option value="">전체 화주사</option>
          {vendorOptions.map(v => <option key={v} value={v}>{v}</option>)}
        </select>
        <input
          type="date"
          value={filterDateFrom}
          onChange={e => setFilterDateFrom(e.target.value)}
          style={{ border: `1px solid ${C.border}`, borderRadius: 6, padding: '0.4rem 0.6rem', fontSize: '0.85rem' }}
        />
        <span style={{ alignSelf: 'center', color: C.muted, fontSize: '0.85rem' }}>~</span>
        <input
          type="date"
          value={filterDateTo}
          onChange={e => setFilterDateTo(e.target.value)}
          style={{ border: `1px solid ${C.border}`, borderRadius: 6, padding: '0.4rem 0.6rem', fontSize: '0.85rem' }}
        />
        <button
          onClick={load}
          style={{ background: C.primary, color: '#fff', border: 'none', borderRadius: 6, padding: '0.4rem 1rem', fontSize: '0.85rem', cursor: 'pointer', fontWeight: 600 }}
        >
          조회
        </button>
        {(filterVendor || filterDateFrom || filterDateTo) && (
          <button
            onClick={() => { setFilterVendor(''); setFilterDateFrom(''); setFilterDateTo(''); }}
            style={{ background: 'none', color: C.muted, border: `1px solid ${C.border}`, borderRadius: 6, padding: '0.4rem 0.8rem', fontSize: '0.85rem', cursor: 'pointer' }}
          >
            초기화
          </button>
        )}
        <span style={{ alignSelf: 'center', marginLeft: 'auto', fontSize: '0.8rem', color: C.muted }}>총 {total}건</span>
      </div>

      {error && (
        <div style={{ background: C.dangerLight, color: C.danger, padding: '0.75rem 1rem', borderRadius: 8, marginBottom: '1rem', fontSize: '0.85rem' }}>
          {error}
        </div>
      )}

      {/* 목록 */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: C.muted }}>불러오는 중...</div>
      ) : items.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: C.muted }}>
          <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>📦</div>
          <div>입고 데이터가 없습니다.</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {items.map(item => {
            const key = `${item.vendor}__${item.inbound_date}`;
            const isSelected = selected?.vendor === item.vendor && selected?.date === item.inbound_date;
            const missingRate = item.total_janggi_qty > 0
              ? Math.round((item.total_missing_qty / item.total_janggi_qty) * 100)
              : 0;

            return (
              <div key={key}>
                <div
                  onClick={() => setSelected(isSelected ? null : { vendor: item.vendor, date: item.inbound_date })}
                  style={{
                    background: isSelected ? C.primaryLight : C.card,
                    border: `1px solid ${isSelected ? C.primary : C.border}`,
                    borderRadius: isSelected ? '8px 8px 0 0' : 8,
                    padding: '0.85rem 1rem',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    flexWrap: 'wrap',
                    transition: 'background 0.15s',
                  }}
                >
                  {/* 날짜 */}
                  <div style={{ minWidth: 90 }}>
                    <div style={{ fontWeight: 700, fontSize: '0.95rem', color: C.text }}>{fmtDate(item.inbound_date)}</div>
                    <div style={{ fontSize: '0.72rem', color: C.muted }}>{item.inbound_date}</div>
                  </div>

                  {/* 화주사 */}
                  <div style={{ minWidth: 120 }}>
                    <div style={{ fontWeight: 600, fontSize: '0.9rem', color: C.primary }}>{item.vendor}</div>
                    <div style={{ fontSize: '0.72rem', color: C.muted }}>도매처 {item.batches_count}곳</div>
                  </div>

                  {/* 도매처 태그 */}
                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', flex: 1 }}>
                    {item.wholesales.map(w => w && (
                      <span key={w} style={{ background: '#f1f5f9', border: `1px solid ${C.border}`, borderRadius: 4, padding: '1px 7px', fontSize: '0.75rem', color: C.textSub }}>
                        {w}
                      </span>
                    ))}
                  </div>

                  {/* 수량 요약 */}
                  <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: '0.68rem', color: C.muted }}>장끼</div>
                      <div style={{ fontWeight: 700, fontSize: '0.95rem', color: C.text }}>{item.total_janggi_qty.toLocaleString()}</div>
                    </div>
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: '0.68rem', color: C.muted }}>실수량</div>
                      <div style={{ fontWeight: 700, fontSize: '0.95rem', color: C.success }}>{item.total_actual_qty.toLocaleString()}</div>
                    </div>
                    {item.total_missing_qty > 0 && (
                      <div style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: '0.68rem', color: C.muted }}>누락</div>
                        <div style={{ fontWeight: 700, fontSize: '0.95rem', color: C.danger }}>{item.total_missing_qty.toLocaleString()}</div>
                      </div>
                    )}
                    {missingRate > 0 && (
                      <div style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: '0.68rem', color: C.muted }}>누락률</div>
                        <div style={{ fontWeight: 700, fontSize: '0.9rem', color: C.danger }}>{missingRate}%</div>
                      </div>
                    )}
                  </div>

                  {/* 상태 */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    {statusChip(item.statuses, item.all_closed)}
                    <span style={{ color: C.muted, fontSize: '0.85rem' }}>{isSelected ? '▲' : '▼'}</span>
                  </div>
                </div>

                {/* 상세 패널 */}
                {isSelected && (
                  <div style={{ border: `1px solid ${C.primary}`, borderTop: 'none', borderRadius: '0 0 8px 8px', overflow: 'hidden' }}>
                    <DetailPanel
                      vendor={item.vendor}
                      date={item.inbound_date}
                      onClose={() => setSelected(null)}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
