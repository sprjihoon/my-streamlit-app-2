'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Alert from '@/components/Alert';
import Card from '@/components/Card';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import { ConfirmDialog } from '@/components/domestic/ConfirmDialog';
import { CopyButton } from '@/components/domestic/CopyButton';
import {
  cancelDomesticShipping,
  deleteDomesticShipping,
  listDomesticShipments,
  type DomesticShipment,
} from '@/lib/api';
import {
  classifyDomesticError,
  domesticStatusLabel,
  emptyListFilters,
  filterShipments,
  filtersActive,
  readListFilters,
  replaceListFilters,
  type ListFilters,
} from '@/lib/domestic-form';

type Pending = { kind: 'cancel' | 'delete'; item: DomesticShipment } | null;

function cancelCopy(item: DomesticShipment) {
  const no = item.tracking_no || item.order_no;
  return item.is_test
    ? `송장 ${no} 테스트 접수를 취소할까요? 우체국에는 취소 요청을 보내지 않습니다.`
    : `송장 ${no} 접수를 취소할까요? 실접수는 우체국 접수도 함께 취소합니다.`;
}

function deleteCopy(item: DomesticShipment) {
  const no = item.tracking_no || item.order_no;
  const live = item.status !== 'canceled' && !item.is_test;
  return live
    ? `송장 ${no} 접수를 우체국에서 취소한 뒤 목록에서 삭제할까요?`
    : `송장 ${no} 접수를 목록에서 삭제할까요?`;
}

export default function DomesticShippingListPage() {
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [items, setItems] = useState<DomesticShipment[]>([]);
  const [isAdmin, setIsAdmin] = useState(false);
  const [filters, setFilters] = useState<ListFilters>(emptyListFilters);
  const [pending, setPending] = useState<Pending>(null);
  const [acting, setActing] = useState(false);
  const actingRef = useRef(false);

  async function load(tok: string) {
    const res = await listDomesticShipments(tok);
    setItems(res.items || []);
    setLoadError(null);
    setLoaded(true);
  }

  useEffect(() => {
    setFilters(readListFilters(window.location.search));
    const stored = localStorage.getItem('token') || '';
    setToken(stored);
    setIsAdmin(localStorage.getItem('isAdmin') === 'true');
    if (!stored) {
      setLoadError('로그인이 필요합니다.');
      setLoaded(true);
      setLoading(false);
      return;
    }
    load(stored).catch((err) => {
      setLoadError(classifyDomesticError(err, 'shipment').message);
      setLoaded(true);
    }).finally(() => setLoading(false));
  }, []);

  function updateFilters(next: ListFilters) {
    setFilters(next);
    replaceListFilters(next);
  }

  const filtered = useMemo(() => filterShipments(items, filters), [items, filters]);
  const vendorOptions = useMemo(() => {
    const map = new Map<number, string>();
    items.forEach((item) => {
      if (item.vendor_id) map.set(item.vendor_id, item.vendor_name || String(item.vendor_id));
    });
    return Array.from(map, ([id, name]) => ({ id, name }));
  }, [items]);
  const searching = filtersActive(filters);

  function detailHref(id: number) {
    const query = window.location.search;
    return `/domestic-shipping-list/${id}${query}`;
  }

  function dismissPending() {
    if (actingRef.current) return;
    setPending(null);
  }

  async function confirmPending() {
    if (!pending || actingRef.current) return;
    actingRef.current = true;
    setActing(true);
    setError(null);
    setSuccess(null);
    try {
      const result = pending.kind === 'cancel'
        ? await cancelDomesticShipping(token, pending.item.id)
        : await deleteDomesticShipping(token, pending.item.id);
      setSuccess(result.message || (pending.kind === 'cancel' ? '취소했습니다.' : '삭제했습니다.'));
      setPending(null);
      await load(token);
    } catch (err) {
      setError(classifyDomesticError(err, 'shipment').message);
      setPending(null);
    } finally {
      actingRef.current = false;
      setActing(false);
    }
  }

  if (loading && !loaded) return <Loading text="출고 목록을 불러오는 중..." />;

  return (
    <div className="domestic-page">
      <PageHeader
        title="출고 목록"
        subtitle={loaded && !loadError ? (searching ? `검색 결과 ${filtered.length}건 · 전체 ${items.length}건` : `${items.length}건`) : undefined}
        actions={(
          <>
            <a href="/domestic-shipping" className="btn btn-primary">새 접수</a>
            <a href="/domestic-vendors" className="btn btn-secondary">업체 등록</a>
          </>
        )}
      />
      {loadError ? (
        <Alert type="error">
          {loadError}{' '}
          <button type="button" className="btn btn-secondary" onClick={() => {
            setLoading(true);
            load(token).catch((err) => {
              setLoadError(classifyDomesticError(err, 'shipment').message);
            }).finally(() => setLoading(false));
          }}>
            다시 불러오기
          </button>
        </Alert>
      ) : null}
      {error ? <Alert type="error">{error}</Alert> : null}
      {success ? <Alert type="success">{success}</Alert> : null}
      <Card>
        <div className="domestic-filters">
          <label>
            검색
            <input
              value={filters.q}
              placeholder="송장번호, 접수번호, 수취인, 업체"
              onChange={(event) => updateFilters({ ...filters, q: event.target.value })}
            />
          </label>
          <label>
            업체
            <select value={filters.vendor} onChange={(event) => updateFilters({ ...filters, vendor: event.target.value })}>
              <option value="">전체</option>
              {vendorOptions.map((vendor) => (
                <option key={vendor.id} value={vendor.id}>{vendor.name}</option>
              ))}
            </select>
          </label>
          <label>
            시작
            <input type="date" value={filters.from} onChange={(event) => updateFilters({ ...filters, from: event.target.value })} />
          </label>
          <label>
            종료
            <input type="date" value={filters.to} onChange={(event) => updateFilters({ ...filters, to: event.target.value })} />
          </label>
          <label>
            상태
            <select
              value={filters.status}
              onChange={(event) => updateFilters({ ...filters, status: event.target.value as ListFilters['status'] })}
            >
              <option value="">전체</option>
              <option value="requested">접수</option>
              <option value="test">테스트</option>
              <option value="canceled">취소</option>
            </select>
          </label>
          {searching ? (
            <button type="button" className="btn btn-ghost" onClick={() => updateFilters(emptyListFilters())}>
              초기화
            </button>
          ) : null}
        </div>

        {loadError && items.length === 0 ? null : items.length === 0 ? (
          <p className="text-muted">접수 내역이 없습니다.</p>
        ) : filtered.length === 0 ? (
          <p className="text-muted">검색 결과가 없습니다.</p>
        ) : (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>접수일</th><th>업체</th><th>수취인</th><th>송장번호</th><th>요금</th><th>상태</th><th>접수자</th><th>관리</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => (
                  <tr key={item.id} className="domestic-list-row" onClick={() => { window.location.href = detailHref(item.id); }}>
                    <td>{(item.created_at || '').replace('T', ' ').slice(0, 16)}</td>
                    <td>{item.vendor_name}</td>
                    <td>{item.recipient_name}</td>
                    <td><CopyButton value={item.tracking_no || ''} /></td>
                    <td>{item.price || '-'}</td>
                    <td>{domesticStatusLabel(item)}</td>
                    <td>{item.created_by}</td>
                    <td onClick={(event) => event.stopPropagation()}>
                      <div className="domestic-row-actions">
                        <a className="btn btn-secondary" href={`/domestic-print/${item.id}`} target="_blank" rel="noreferrer">송장</a>
                        {item.status !== 'canceled' ? (
                          <button type="button" className="btn btn-warning" onClick={() => setPending({ kind: 'cancel', item })}>접수 취소</button>
                        ) : null}
                        {isAdmin ? (
                          <button type="button" className="btn btn-danger" onClick={() => setPending({ kind: 'delete', item })}>삭제</button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <ConfirmDialog
        open={Boolean(pending)}
        title={pending?.kind === 'delete' ? '목록에서 삭제' : '접수 취소'}
        description={pending ? (pending.kind === 'delete' ? deleteCopy(pending.item) : cancelCopy(pending.item)) : ''}
        confirmLabel={pending?.kind === 'delete' ? '삭제' : '접수 취소'}
        confirmClass={pending?.kind === 'delete' ? 'btn btn-danger' : 'btn btn-warning'}
        busy={acting}
        busyLabel="처리 중..."
        onDismiss={dismissPending}
        onConfirm={() => void confirmPending()}
      />
    </div>
  );
}
