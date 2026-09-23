'use client';

import { useEffect, useState } from 'react';
import Card from '@/components/Card';
import Alert from '@/components/Alert';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import {
  cancelOverseasShipping,
  deleteOverseasShipping,
  listOverseasShipments,
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
  const [query, setQuery] = useState('');
  const [isAdmin, setIsAdmin] = useState(false);

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

  async function handleDelete(item: OverseasShippingItem) {
    const live = item.status !== 'canceled' && !item.is_test;
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

  async function handleCancel(item: OverseasShippingItem) {
    if (!window.confirm(`등기번호 ${item.tracking_no || item.order_no} 접수를 취소할까요?`)) return;
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

  if (loading) return <Loading text="해외배송 목록 로딩 중..." />;

  const q = query.trim().toLowerCase().replace(/\s+/g, '');
  const visible = q
    ? items.filter((it) => (
      `${it.order_no} ${it.tracking_no} ${it.recipient_name} ${it.countrycd} ${it.shipping_method} ${it.contents_label || ''} ${it.created_by}`
        .toLowerCase()
        .replace(/\s+/g, '')
        .includes(q)
    ))
    : items;

  return (
    <div className="overseas-page">
      <PageHeader
        title="해외배송 접수목록"
        subtitle="행을 누르면 입력값을 그대로 봅니다. 지출은 요금, DDP, 합계입니다."
      />
      {error && <Alert type="error">{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}

      <Card title={`해외배송 목록 · 전체 ${items.length}건`}>
        <div style={{ marginBottom: '1rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <a href="/overseas-shipping" className="btn btn-primary">새 접수</a>
          <a href="/overseas-senders" className="btn btn-secondary">발송인</a>
          <a href="/overseas-recipients" className="btn btn-secondary">수취인</a>
          <a href="/overseas-hs-codes" className="btn btn-secondary">HS코드</a>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="등기번호, 수취인, 국가 검색"
            style={{
              marginLeft: 'auto',
              minWidth: 220,
              padding: '0.5rem 0.7rem',
              border: '1px solid var(--border)',
              borderRadius: 8,
              fontFamily: 'inherit',
            }}
          />
        </div>
        {items.length === 0 ? (
          <p className="text-muted">접수 내역이 없습니다.</p>
        ) : visible.length === 0 ? (
          <p className="text-muted">검색 결과가 없습니다.</p>
        ) : (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>접수일</th>
                  <th>배송</th>
                  <th>국가</th>
                  <th>수취인</th>
                  <th>등기번호</th>
                  <th>지출</th>
                  <th>상태</th>
                  <th>접수자</th>
                  <th>출력서류</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((it) => (
                  <tr
                    key={it.id}
                    onClick={() => { window.location.href = `/overseas-shipping-list/${it.id}`; }}
                    style={{ cursor: 'pointer' }}
                  >
                    <td>{(it.created_at || '').replace('T', ' ').slice(0, 16)}</td>
                    <td>{METHOD_LABEL[it.shipping_method] || it.shipping_method}{it.contents_label ? ` · ${it.contents_label}` : ''}</td>
                    <td>{it.countrycd}</td>
                    <td>{it.recipient_name}</td>
                    <td style={{ fontFamily: 'monospace' }}>{it.tracking_no || '-'}</td>
                    <td style={{ whiteSpace: 'nowrap', lineHeight: 1.45, fontSize: '0.85rem' }}>
                      <div>요금 {won(it.ems_fee)}</div>
                      <div>DDP {won(it.ddp_krw)}</div>
                      <div><strong>합계 {won(it.spent_total)}</strong></div>
                    </td>
                    <td>{it.status === 'canceled' ? '취소' : it.is_test ? '테스트' : '접수'}</td>
                    <td>{it.created_by}</td>
                    <td style={{ whiteSpace: 'nowrap' }} onClick={(e) => e.stopPropagation()}>
                      <a href={`/overseas-print/${it.id}`} className="btn btn-primary" target="_blank" rel="noreferrer">
                        출력서류
                      </a>
                      {it.status !== 'canceled' && (
                        <button type="button" className="btn btn-secondary" style={{ marginLeft: '0.35rem' }} onClick={() => handleCancel(it)}>
                          취소
                        </button>
                      )}
                      {isAdmin && (
                        <button type="button" className="btn btn-secondary" style={{ marginLeft: '0.35rem' }} onClick={() => handleDelete(it)}>
                          삭제
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
