'use client';

import { useEffect, useMemo, useState } from 'react';
import Card from '@/components/Card';
import Alert from '@/components/Alert';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import { CopyButton } from '@/components/domestic/CopyButton';
import {
  cancelOverseasShipping,
  deleteOverseasShipping,
  listOverseasShipments,
  canCancelOverseas,
  overseasStatusLabel,
  refreshOverseasShippingStatuses,
  resubmitOverseasShipping,
  type OverseasShippingItem,
} from '@/lib/api';

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

const METHOD_LABEL: Record<string, string> = {
  EMS: 'EMS',
  EMS_PREMIUM: 'EMS 프리미엄',
  KPACKET: 'K-Packet',
};

const PAGE_SIZES = [10, 30, 50, 100];

type StatusFilter = '' | 'requested' | 'transit' | 'delivered' | 'test' | 'canceled';

type ListFilters = {
  q: string;
  country: string;
  method: string;
  status: StatusFilter;
  from: string;
  to: string;
};

const EMPTY_FILTERS: ListFilters = { q: '', country: '', method: '', status: '', from: '', to: '' };

function pageMarks(totalPages: number, safePage: number): Array<number | '…'> {
  const pages = Array.from({ length: totalPages }, (_, index) => index + 1)
    .filter((page) => page === 1 || page === totalPages || Math.abs(page - safePage) <= 2);
  return pages.reduce<Array<number | '…'>>((marks, page, index) => {
    if (index > 0 && page - pages[index - 1] > 1) marks.push('…');
    marks.push(page);
    return marks;
  }, []);
}

function shipmentDay(item: OverseasShippingItem) {
  return (item.created_at || '').slice(0, 10);
}

function matchesStatus(item: OverseasShippingItem, status: StatusFilter) {
  if (!status) return true;
  if (status === 'canceled') return item.status === 'canceled';
  if (item.status === 'canceled') return false;
  if (status === 'test') return item.is_test;
  if (item.is_test) return false;
  const treat = (item.treat_status || item.treat_status_name || '').trim();
  if (status === 'delivered') return treat === '배달완료';
  if (status === 'requested') return !treat;
  return Boolean(treat) && treat !== '배달완료';
}

function filtersActive(filters: ListFilters) {
  return Boolean(filters.q || filters.country || filters.method || filters.status || filters.from || filters.to);
}

function won(value: number | string | null | undefined): string {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return '-';
  return `${Math.round(n).toLocaleString()}원`;
}

export default function OverseasShippingListPage() {
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [items, setItems] = useState<OverseasShippingItem[]>([]);
  const [filters, setFilters] = useState<ListFilters>(EMPTY_FILTERS);
  const [pageSize, setPageSize] = useState(30);
  const [currentPage, setCurrentPage] = useState(1);
  const [isAdmin, setIsAdmin] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [resubmittingId, setResubmittingId] = useState<number | null>(null);

  async function loadList(tok: string) {
    const res = await listOverseasShipments(tok);
    setItems(res.items || []);
  }

  useEffect(() => {
    const stored = localStorage.getItem('token') || '';
    setToken(stored);
    setIsAdmin(localStorage.getItem('isAdmin') === 'true');
    if (!stored) {
      setError('로그인이 필요합니다.');
      setLoading(false);
      return;
    }
    (async () => {
      try {
        await loadList(stored);
      } catch (err) {
        setError(parseApiError(err));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function handleRefreshStatus() {
    if (!token || refreshing) return;
    setRefreshing(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await refreshOverseasShippingStatuses(token);
      await loadList(token);
      setSuccess(result.message || `등기조회 완료. 배달완료 ${result.delivered}건`);
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setRefreshing(false);
    }
  }

  async function handleDelete(item: OverseasShippingItem) {
    const live = item.status !== 'canceled' && !item.is_test && canCancelOverseas(item);
    const ask = live
      ? `등기번호 ${item.tracking_no || item.order_no} 접수를 우체국에서 취소한 뒤 목록에서 삭제할까요?`
      : `등기번호 ${item.tracking_no || item.order_no} 접수를 목록에서 삭제할까요?`;
    if (!window.confirm(ask)) return;
    setError(null);
    setSuccess(null);
    try {
      const result = await deleteOverseasShipping(token, item.id);
      setSuccess(result.message || '삭제했습니다.');
      await loadList(token);
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  async function handleResubmit(item: OverseasShippingItem) {
    const ok = window.confirm(
      `이 내용으로 새 해외배송을 접수할까요?\n\n` +
      `발송인: ${item.sender_name || '-'}\n` +
      `수취인: ${item.recipient_name} / ${item.countrycd}\n` +
      `배송: ${METHOD_LABEL[item.shipping_method] || item.shipping_method}` +
      `${item.contents_label ? ` · ${item.contents_label}` : ''}\n` +
      `예전 등기번호 ${item.tracking_no || '-'} 는 그대로 두고, 우체국에 새 접수로 나갑니다.`,
    );
    if (!ok) return;
    setResubmittingId(item.id);
    setError(null);
    setSuccess(null);
    try {
      const result = await resubmitOverseasShipping(token, item.id);
      if (result.duplicate_guard) {
        setError(`오늘 같은 수취인으로 이미 접수된 건이 있어 이번 재접수는 우체국으로 나가지 않았습니다. 등기번호 ${result.tracking_no}`);
        return;
      }
      setSuccess(`재접수 완료. 등기번호 ${result.tracking_no}${result.is_test ? ' (테스트)' : ''}`);
      await loadList(token);
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setResubmittingId(null);
    }
  }

  async function handleCancel(item: OverseasShippingItem) {
    if (!window.confirm(`등기번호 ${item.tracking_no || item.order_no} 접수를 취소할까요?\n우체국에 접수된 건은 우체국 접수도 함께 취소합니다.`)) return;
    setError(null);
    setSuccess(null);
    try {
      const result = await cancelOverseasShipping(token, item.id);
      setSuccess(result.message || '취소했습니다.');
      await loadList(token);
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  const countries = useMemo(
    () => Array.from(new Set(items.map((item) => item.countrycd).filter(Boolean))).sort(),
    [items],
  );
  const filtered = useMemo(() => {
    const q = filters.q.trim().toLowerCase().replace(/\s+/g, '');
    return items.filter((it) => {
      if (filters.country && it.countrycd !== filters.country) return false;
      if (filters.method && it.shipping_method !== filters.method) return false;
      if (!matchesStatus(it, filters.status)) return false;
      const day = shipmentDay(it);
      if (filters.from && day && day < filters.from) return false;
      if (filters.to && day && day > filters.to) return false;
      if (!q) return true;
      return `${it.order_no} ${it.tracking_no} ${it.sender_name || ''} ${it.recipient_name} ${it.countrycd} ${it.shipping_method} ${it.contents_label || ''} ${it.created_by} ${overseasStatusLabel(it)}`
        .toLowerCase()
        .replace(/\s+/g, '')
        .includes(q);
    });
  }, [filters, items]);
  const totalPages = filtered.length === 0 ? 0 : Math.ceil(filtered.length / pageSize);
  const safePage = totalPages === 0 ? 1 : Math.min(currentPage, totalPages);
  const pageItems = filtered.slice((safePage - 1) * pageSize, safePage * pageSize);

  function updateFilters(next: ListFilters) {
    setFilters(next);
    setCurrentPage(1);
  }

  if (loading) return <Loading text="해외배송 목록 로딩 중..." />;

  return (
    <div className="overseas-page">
      <PageHeader
        title="해외배송 접수목록"
        subtitle="송장조회로 국제우편 배송상태를 받습니다. 지출은 요금, DDP, 합계입니다."
      />
      {error && <Alert type="error">{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}

      <Card title={`해외배송 목록 · 전체 ${items.length}건${filtersActive(filters) ? ` · 결과 ${filtered.length}건` : ''}`}>
        <div style={{ marginBottom: '0.75rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <a href="/overseas-shipping" className="btn btn-primary">새 접수</a>
          <a href="/overseas-senders" className="btn btn-secondary">발송인</a>
          <a href="/overseas-recipients" className="btn btn-secondary">수취인</a>
          <a href="/overseas-hs-codes" className="btn btn-secondary">HS코드</a>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => void handleRefreshStatus()}
            disabled={!token || refreshing}
          >
            {refreshing ? '송장조회 중...' : '송장조회'}
          </button>
        </div>
        <div className="overseas-filters">
          <label>
            검색
            <input
              value={filters.q}
              onChange={(e) => updateFilters({ ...filters, q: e.target.value })}
              placeholder="등기번호, 발송인, 수취인, 국가, 상태"
            />
          </label>
          <label>
            국가
            <select value={filters.country} onChange={(e) => updateFilters({ ...filters, country: e.target.value })}>
              <option value="">전체</option>
              {countries.map((code) => <option key={code} value={code}>{code}</option>)}
            </select>
          </label>
          <label>
            배송
            <select value={filters.method} onChange={(e) => updateFilters({ ...filters, method: e.target.value })}>
              <option value="">전체</option>
              <option value="EMS">EMS</option>
              <option value="EMS_PREMIUM">EMS 프리미엄</option>
              <option value="KPACKET">K-Packet</option>
            </select>
          </label>
          <label>
            상태
            <select value={filters.status} onChange={(e) => updateFilters({ ...filters, status: e.target.value as StatusFilter })}>
              <option value="">전체</option>
              <option value="requested">접수</option>
              <option value="transit">운송중</option>
              <option value="delivered">배달완료</option>
              <option value="test">테스트</option>
              <option value="canceled">취소</option>
            </select>
          </label>
          <label>
            시작
            <input type="date" value={filters.from} onChange={(e) => updateFilters({ ...filters, from: e.target.value })} />
          </label>
          <label>
            종료
            <input type="date" value={filters.to} onChange={(e) => updateFilters({ ...filters, to: e.target.value })} />
          </label>
          {filtersActive(filters) ? (
            <button type="button" className="btn btn-ghost" onClick={() => updateFilters(EMPTY_FILTERS)}>초기화</button>
          ) : null}
        </div>
        {items.length === 0 ? (
          <p className="text-muted">접수 내역이 없습니다.</p>
        ) : filtered.length === 0 ? (
          <p className="text-muted">검색 결과가 없습니다.</p>
        ) : (
          <>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.6rem', flexWrap: 'wrap' }}>
            <span className="text-muted" style={{ fontSize: '0.85rem' }}>
              {(safePage - 1) * pageSize + 1}–{Math.min(safePage * pageSize, filtered.length)} / {filtered.length}건
            </span>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.85rem' }}>
              페이지당
              <select
                value={pageSize}
                onChange={(event) => {
                  setPageSize(Number(event.target.value));
                  setCurrentPage(1);
                }}
              >
                {PAGE_SIZES.map((size) => <option key={size} value={size}>{size}건</option>)}
              </select>
            </label>
          </div>
          <div className="table-container overseas-list-table">
            <table>
              <thead>
                <tr>
                  <th>접수일</th>
                  <th>배송</th>
                  <th>국가</th>
                  <th>발송인</th>
                  <th>수취인</th>
                  <th>등기번호</th>
                  <th>지출</th>
                  <th>상태</th>
                  <th>접수자</th>
                  <th className="overseas-list-actions">관리</th>
                </tr>
              </thead>
              <tbody>
                {pageItems.map((it) => (
                  <tr
                    key={it.id}
                    onClick={() => { window.location.href = `/overseas-shipping-list/${it.id}`; }}
                    style={{ cursor: 'pointer' }}
                  >
                    <td>{(it.created_at || '').replace('T', ' ').slice(0, 16)}</td>
                    <td>{METHOD_LABEL[it.shipping_method] || it.shipping_method}{it.contents_label ? ` · ${it.contents_label}` : ''}</td>
                    <td>{it.countrycd}</td>
                    <td>{it.sender_name || '-'}</td>
                    <td>{it.recipient_name}</td>
                    <td><CopyButton value={it.tracking_no || ''} /></td>
                    <td style={{ whiteSpace: 'nowrap', lineHeight: 1.45, fontSize: '0.85rem' }}>
                      <div>요금 {won(it.ems_fee)}</div>
                      <div>DDP {won(it.ddp_krw)}</div>
                      <div><strong>합계 {won(it.spent_total)}</strong></div>
                    </td>
                    <td>{overseasStatusLabel(it)}</td>
                    <td>{it.created_by}</td>
                    <td className="overseas-list-actions" onClick={(e) => e.stopPropagation()}>
                      <a href={`/overseas-print/${it.id}`} className="btn btn-secondary" target="_blank" rel="noreferrer">
                        출력서류
                      </a>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ marginLeft: '0.35rem' }}
                        disabled={resubmittingId === it.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          void handleResubmit(it);
                        }}
                      >
                        {resubmittingId === it.id ? '재접수 중...' : '재접수'}
                      </button>
                      {canCancelOverseas(it) && (
                        <button
                          type="button"
                          className="btn btn-primary"
                          style={{ marginLeft: '0.35rem' }}
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleCancel(it);
                          }}
                        >
                          접수 취소
                        </button>
                      )}
                      {isAdmin && (
                        <button
                          type="button"
                          className="btn btn-secondary"
                          style={{ marginLeft: '0.35rem' }}
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleDelete(it);
                          }}
                        >
                          삭제
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
            {totalPages > 1 ? (
              <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '0.3rem', marginTop: '0.75rem', flexWrap: 'wrap' }}>
                <button type="button" className="btn btn-secondary" style={{ padding: '0.3rem 0.6rem' }} disabled={safePage === 1} onClick={() => setCurrentPage(1)}>«</button>
                <button type="button" className="btn btn-secondary" style={{ padding: '0.3rem 0.6rem' }} disabled={safePage === 1} onClick={() => setCurrentPage((page) => page - 1)}>‹</button>
                {pageMarks(totalPages, safePage).map((mark, index) => (
                  mark === '…' ? (
                    <span key={`ellipsis-${index}`} style={{ padding: '0 0.3rem', color: 'var(--text-muted)' }}>…</span>
                  ) : (
                    <button
                      key={mark}
                      type="button"
                      className="btn btn-secondary"
                      style={{ padding: '0.3rem 0.6rem', ...(mark === safePage ? { background: 'var(--primary)', color: '#fff', borderColor: 'var(--primary)' } : {}) }}
                      onClick={() => setCurrentPage(mark)}
                    >
                      {mark}
                    </button>
                  )
                ))}
                <button type="button" className="btn btn-secondary" style={{ padding: '0.3rem 0.6rem' }} disabled={safePage === totalPages} onClick={() => setCurrentPage((page) => page + 1)}>›</button>
                <button type="button" className="btn btn-secondary" style={{ padding: '0.3rem 0.6rem' }} disabled={safePage === totalPages} onClick={() => setCurrentPage(totalPages)}>»</button>
              </div>
            ) : null}
          </>
        )}
      </Card>
    </div>
  );
}
