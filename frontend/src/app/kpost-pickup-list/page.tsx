'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import Card from '@/components/Card';
import Alert from '@/components/Alert';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import {
  cancelKpostPickup,
  deleteKpostPickup,
  getKpostPickupFilterOptions,
  listKpostPickups,
  refreshKpostPickupStatuses,
  type KpostPickupItem,
} from '@/lib/api';

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '0.55rem 0.7rem',
  border: '1px solid var(--border)',
  borderRadius: '8px',
  fontFamily: 'inherit',
  fontSize: '0.9rem',
};

function parseApiError(err: unknown): string {
  if (err instanceof Error) {
    const msg = err.message;
    try {
      const parsed = JSON.parse(msg);
      if (typeof parsed?.detail === 'string') return parsed.detail;
    } catch {
      /* ignore */
    }
    return msg;
  }
  return String(err);
}

function statusLabel(item: KpostPickupItem): string {
  if (item.status === 'canceled') return '취소';
  // treat_status 코드 우선, 없으면 treat_status_name 텍스트로 fallback
  const code = item.treat_status;
  if (code === '03') return '배달완료';
  if (code === '07') return '배달중';
  if (code === '06') return '배달준비';
  if (code === '02') return '이동중';
  if (code === '01' || item.treat_status_name === '집하완료') return '수거완료';
  if (code === '05') return '수거준비';
  if (code === '04') return '운송장출력';
  if (code === '00') return '신청접수';
  // 레거시 treat_status_name 텍스트 매핑
  const nm = item.treat_status_name || '';
  if (nm === '수거중' || nm === '이동중') return '이동중';
  if (nm === '배달준비') return '배달준비';
  if (nm === '배달중') return '배달중';
  if (nm === '수거완료' || nm === '집하완료') return '수거완료';
  if (nm === '배달완료') return '배달완료';
  return nm || item.status || '신청접수';
}

const STATUS_CHIP: Record<string, React.CSSProperties> = {
  // ── 수거 전 단계 ───────────────────────────────────
  '신청접수':  { background: '#f1f5f9', color: '#475569', border: '1px solid #cbd5e1' },
  '운송장출력': { background: '#fefce8', color: '#854d0e', border: '1px solid #fde68a' },
  '수거준비':  { background: '#fff7ed', color: '#c2410c', border: '1px solid #fed7aa' },
  // ── 수거 완료 ─────────────────────────────────────
  '수거완료':  { background: '#f0fdf4', color: '#15803d', border: '1px solid #bbf7d0', fontWeight: 700 },
  // ── 배송 중 ───────────────────────────────────────
  '이동중':    { background: '#eff6ff', color: '#1d4ed8', border: '1px solid #bfdbfe' },
  '수거중':    { background: '#eff6ff', color: '#1d4ed8', border: '1px solid #bfdbfe' }, // 레거시
  '배달준비':  { background: '#f5f3ff', color: '#6d28d9', border: '1px solid #ddd6fe' },
  '배달중':    { background: '#fdf4ff', color: '#86198f', border: '1px solid #f0abfc' },
  // ── 최종 ──────────────────────────────────────────
  '배달완료':  { background: '#ecfdf5', color: '#0f766e', border: '1px solid #99f6e4', fontWeight: 700 },
  '취소':      { background: '#fef2f2', color: '#991b1b', border: '1px solid #fecaca' },
};

function StatusChip({ label }: { label: string }) {
  const style: React.CSSProperties = {
    display: 'inline-block',
    padding: '0.2rem 0.55rem',
    borderRadius: '999px',
    fontSize: '0.78rem',
    whiteSpace: 'nowrap',
    ...(STATUS_CHIP[label] ?? { background: '#f8fafc', color: '#64748b', border: '1px solid #e2e8f0' }),
  };
  return <span style={style}>{label}</span>;
}

function canCancel(item: KpostPickupItem): boolean {
  return item.status === 'requested' && item.treat_status !== '01' && item.treat_status !== '03';
}

export default function KpostPickupListPage() {
  const [token, setToken] = useState('');
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefreshing, setAutoRefreshing] = useState(false);
  const autoRefreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const tokenRef = useRef('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [items, setItems] = useState<KpostPickupItem[]>([]);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [recipientFilter, setRecipientFilter] = useState('');
  const [createdByFilter, setCreatedByFilter] = useState('');
  const [createdByOptions, setCreatedByOptions] = useState<string[]>([]);
  const [recipientOptions, setRecipientOptions] = useState<string[]>([]);
  const [pageSize, setPageSize] = useState(30);
  const [currentPage, setCurrentPage] = useState(1);
  const [sortKey, setSortKey] = useState<string>('id');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const loadList = useCallback(
    async (auth: string, filters?: { dateFrom?: string; dateTo?: string; recipientName?: string; createdBy?: string }) => {
      const data = await listKpostPickups(auth, filters);
      setItems(data.items || []);
    },
    []
  );

  function currentFilters() {
    return {
      dateFrom: dateFrom || undefined,
      dateTo: dateTo || undefined,
      recipientName: recipientFilter || undefined,
      createdBy: createdByFilter || undefined,
    };
  }

  // 백그라운드에서 우체국 API를 호출해 상태를 갱신하고, 완료 후 목록을 다시 불러온다.
  const silentRefresh = useCallback(async (auth: string) => {
    if (!auth) return;
    setAutoRefreshing(true);
    try {
      await refreshKpostPickupStatuses(auth);
      await loadList(auth);
    } catch {
      // 자동 조회 실패는 조용히 무시 (수동 조회로 에러 확인 가능)
    } finally {
      setAutoRefreshing(false);
    }
  }, [loadList]);

  useEffect(() => {
    const stored = localStorage.getItem('token') || '';
    tokenRef.current = stored;
    setToken(stored);
    const adminFlag = localStorage.getItem('is_admin');
    setIsAdmin(adminFlag === 'true' || adminFlag === '1');
    if (!stored) {
      setError('로그인이 필요합니다.');
      setLoading(false);
      return;
    }
    (async () => {
      try {
        const [, opts] = await Promise.all([
          loadList(stored),
          getKpostPickupFilterOptions(stored).catch(() => ({ created_by: [], recipient_names: [] })),
        ]);
        setCreatedByOptions(opts.created_by || []);
        setRecipientOptions(opts.recipient_names || []);
      } catch (err) {
        setError(parseApiError(err));
      } finally {
        setLoading(false);
      }
      // 초기 로드 직후 백그라운드 자동 조회 (최신 상태 즉시 반영)
      silentRefresh(stored);
    })();

    // 60초마다 자동 갱신
    autoRefreshTimerRef.current = setInterval(() => {
      silentRefresh(tokenRef.current);
    }, 60_000);

    return () => {
      if (autoRefreshTimerRef.current) clearInterval(autoRefreshTimerRef.current);
    };
  }, [loadList, silentRefresh]);

  function handleSort(key: string) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
    setCurrentPage(1);
  }

  function sortedItems() {
    const dir = sortDir === 'asc' ? 1 : -1;
    return [...items].sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[sortKey] ?? '';
      const bv = (b as unknown as Record<string, unknown>)[sortKey] ?? '';
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return 0;
    });
  }

  function SortTh({ col, label, style }: { col: string; label: string; style?: React.CSSProperties }) {
    const active = sortKey === col;
    return (
      <th
        onClick={() => handleSort(col)}
        style={{ cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap', ...style }}
      >
        {label}{' '}
        <span style={{ opacity: active ? 1 : 0.25, fontSize: '0.7rem' }}>
          {active ? (sortDir === 'asc' ? '▲' : '▼') : '▲▼'}
        </span>
      </th>
    );
  }

  async function handleFilter() {
    setError(null);
    setCurrentPage(1);
    try {
      await loadList(token, currentFilters());
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  async function handleShowAll() {
    setDateFrom('');
    setDateTo('');
    setRecipientFilter('');
    setCreatedByFilter('');
    setCurrentPage(1);
    setError(null);
    try {
      await loadList(token);
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  async function handleRefreshStatus() {
    setRefreshing(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await refreshKpostPickupStatuses(token);
      await loadList(token, currentFilters());
      setSuccess(result.message || `송장조회 완료. 수거완료 ${result.completed}건`);
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setRefreshing(false);
    }
  }

  async function handleCancel(id: number, tracking: string) {
    if (!window.confirm(`송장 ${tracking || id} 회수신청을 취소할까요?`)) return;
    setError(null);
    try {
      const result = await cancelKpostPickup(token, id);
      setSuccess(result.message || '회수신청을 취소했습니다.');
      await loadList(token, currentFilters());
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  async function handleDelete(id: number, tracking: string) {
    if (!window.confirm(`송장 ${tracking || id} 접수 내역을 DB에서 완전 삭제할까요?\n이 작업은 되돌릴 수 없습니다.`)) return;
    setError(null);
    try {
      const result = await deleteKpostPickup(token, id);
      setSuccess(`삭제 완료: ${result.tracking_no || id}`);
      await loadList(token, currentFilters());
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  if (loading) return <Loading text="회수신청 목록 로딩 중..." />;

  return (
    <div>
      <PageHeader title="회수신청 목록" subtitle="전체 접수 내역을 보고, 송장조회로 수거완료 여부를 확인합니다." />

      {error && <Alert type="error">{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}

      <Card title={`회수신청 목록 · 전체 ${items.length}건`}>
        <div
          style={{
            marginBottom: '1rem',
            display: 'grid',
            gridTemplateColumns: '1fr 1fr 1fr 1fr auto auto auto',
            gap: '0.5rem',
            alignItems: 'end',
          }}
        >
          <label>
            수거일 (시작)
            <input type="date" style={inputStyle} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label>
            수거일 (종료)
            <input type="date" style={inputStyle} value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>
          <label>
            수취인
            <input
              style={inputStyle}
              value={recipientFilter}
              onChange={(e) => setRecipientFilter(e.target.value)}
              placeholder="이름 입력 또는 선택"
              list="recipient-options"
              autoComplete="off"
            />
            <datalist id="recipient-options">
              {recipientOptions.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </label>
          <label>
            접수자
            <input
              style={inputStyle}
              value={createdByFilter}
              onChange={(e) => setCreatedByFilter(e.target.value)}
              placeholder="이름 입력 또는 선택"
              list="createdby-options"
              autoComplete="off"
            />
            <datalist id="createdby-options">
              {createdByOptions.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </label>
          <button type="button" className="btn btn-secondary" onClick={handleFilter}>
            조회
          </button>
          <button type="button" className="btn btn-secondary" onClick={handleShowAll}>
            전체목록
          </button>
          <button type="button" className="btn btn-primary" onClick={handleRefreshStatus} disabled={refreshing || autoRefreshing}>
            {refreshing ? '송장조회 중...' : '송장조회'}
          </button>
          {autoRefreshing && (
            <span style={{ fontSize: '0.78rem', color: '#64748b', whiteSpace: 'nowrap' }}>
              ⟳ 자동 갱신 중…
            </span>
          )}
        </div>
        {items.length === 0 ? (
          <p className="text-muted">접수 내역이 없습니다.</p>
        ) : (() => {
          const sorted = sortedItems();
          const totalPages = Math.ceil(sorted.length / pageSize);
          const safePage = Math.min(currentPage, totalPages);
          const pageItems = sorted.slice((safePage - 1) * pageSize, safePage * pageSize);
          return (
            <>
              {/* 페이지 크기 + 페이지 정보 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.6rem', flexWrap: 'wrap' }}>
                <span className="text-muted" style={{ fontSize: '0.85rem' }}>
                  {(safePage - 1) * pageSize + 1}–{Math.min(safePage * pageSize, sorted.length)} / {sorted.length}건
                </span>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.85rem' }}>
                  페이지당
                  <select
                    style={{ ...inputStyle, width: 'auto', padding: '0.25rem 0.5rem' }}
                    value={pageSize}
                    onChange={(e) => { setPageSize(Number(e.target.value)); setCurrentPage(1); }}
                  >
                    {[10, 30, 50, 100].map((n) => <option key={n} value={n}>{n}건</option>)}
                  </select>
                </label>
              </div>

              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <SortTh col="tracking_no"   label="수거송장번호" />
                      <SortTh col="recipient_name" label="수취인" />
                      <SortTh col="addr1"          label="주소" />
                      <SortTh col="pickup_date"    label="수거일" />
                      <SortTh col="box_size"       label="박스" />
                      <SortTh col="treat_status"   label="상태" />
                      <SortTh col="created_by"     label="접수자" />
                      <SortTh col="canceled_by"    label="취소자" />
                      <th style={{ whiteSpace: 'nowrap', width: '1%' }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {pageItems.map((item) => {
                      const label = statusLabel(item);
                      return (
                        <tr key={item.id}>
                          <td>
                            <strong>{item.tracking_no || '-'}</strong>
                            {item.is_test ? ' (테스트)' : ''}
                          </td>
                          <td>
                            {item.recipient_name}
                            <div className="text-muted">{item.recipient_phone}</div>
                          </td>
                          <td>
                            [{item.zipcode}] {item.addr1} {item.addr2}
                          </td>
                          <td>{item.pickup_date}</td>
                          <td>
                            {item.box_size} × {item.box_quantity || 1}
                          </td>
                          <td><StatusChip label={label} /></td>
                          <td>
                            {item.created_by || '-'}
                            <div className="text-muted" style={{ fontSize: '0.8rem' }}>{item.created_at?.replace('T', ' ').slice(0, 16)}</div>
                          </td>
                          <td>
                            {item.canceled_by
                              ? (<>{item.canceled_by}<div className="text-muted" style={{ fontSize: '0.8rem' }}>{item.canceled_at?.replace('T', ' ').slice(0, 16)}</div></>)
                              : <span className="text-muted">-</span>}
                          </td>
                          <td style={{ whiteSpace: 'nowrap', verticalAlign: 'middle', width: '1%' }}>
                            <div style={{ display: 'flex', gap: '0.3rem' }}>
                              {canCancel(item) && (
                                <button type="button" className="btn btn-secondary" onClick={() => handleCancel(item.id, item.tracking_no)}>
                                  취소
                                </button>
                              )}
                              {isAdmin && (
                                <button type="button" className="btn btn-secondary" style={{ color: '#dc2626' }} onClick={() => handleDelete(item.id, item.tracking_no)}>
                                  삭제
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* 페이지 네비게이션 */}
              {totalPages > 1 && (
                <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '0.3rem', marginTop: '0.75rem', flexWrap: 'wrap' }}>
                  <button className="btn btn-secondary" style={{ padding: '0.3rem 0.6rem' }} disabled={safePage === 1} onClick={() => setCurrentPage(1)}>«</button>
                  <button className="btn btn-secondary" style={{ padding: '0.3rem 0.6rem' }} disabled={safePage === 1} onClick={() => setCurrentPage((p) => p - 1)}>‹</button>
                  {Array.from({ length: totalPages }, (_, i) => i + 1)
                    .filter((p) => p === 1 || p === totalPages || Math.abs(p - safePage) <= 2)
                    .reduce<(number | string)[]>((acc, p, idx, arr) => {
                      if (idx > 0 && (p as number) - (arr[idx - 1] as number) > 1) acc.push('…');
                      acc.push(p);
                      return acc;
                    }, [])
                    .map((p, i) =>
                      p === '…' ? (
                        <span key={`ellipsis-${i}`} style={{ padding: '0 0.3rem', color: 'var(--text-muted)' }}>…</span>
                      ) : (
                        <button
                          key={p}
                          className="btn btn-secondary"
                          style={{ padding: '0.3rem 0.6rem', ...(p === safePage ? { background: 'var(--primary)', color: '#fff', borderColor: 'var(--primary)' } : {}) }}
                          onClick={() => setCurrentPage(p as number)}
                        >
                          {p}
                        </button>
                      )
                    )}
                  <button className="btn btn-secondary" style={{ padding: '0.3rem 0.6rem' }} disabled={safePage === totalPages} onClick={() => setCurrentPage((p) => p + 1)}>›</button>
                  <button className="btn btn-secondary" style={{ padding: '0.3rem 0.6rem' }} disabled={safePage === totalPages} onClick={() => setCurrentPage(totalPages)}>»</button>
                </div>
              )}
            </>
          );
        })()}
      </Card>
    </div>
  );
}
