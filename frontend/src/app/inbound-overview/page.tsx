'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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
// 메인 페이지
// ─────────────────────────────────────────────
export default function InboundOverviewPage() {
  const router = useRouter();
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
                onClick={() => router.push('/inbound-overview/detail?vendor=' + encodeURIComponent(item.vendor) + '&date=' + item.inbound_date)}
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
