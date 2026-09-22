'use client';

import { useEffect, useState } from 'react';
import Card from '@/components/Card';
import Alert from '@/components/Alert';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import {
  cancelOverseasShipping,
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

export default function OverseasShippingListPage() {
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [items, setItems] = useState<OverseasShippingItem[]>([]);
  const [query, setQuery] = useState('');

  async function loadList(tok: string) {
    const res = await listOverseasShipments(tok);
    setItems(res.items || []);
  }

  useEffect(() => {
    const stored = localStorage.getItem('token') || '';
    setToken(stored);
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
        subtitle="접수한 건은 각 행의 출력서류 버튼으로 언제든 다시 인쇄할 수 있습니다."
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
                  <th>요금</th>
                  <th>상태</th>
                  <th>접수자</th>
                  <th>출력서류</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((it) => (
                  <tr key={it.id}>
                    <td>{(it.created_at || '').replace('T', ' ').slice(0, 16)}</td>
                    <td>{METHOD_LABEL[it.shipping_method] || it.shipping_method}{it.contents_label ? ` · ${it.contents_label}` : ''}</td>
                    <td>{it.countrycd}</td>
                    <td>{it.recipient_name}</td>
                    <td style={{ fontFamily: 'monospace' }}>{it.tracking_no || '-'}</td>
                    <td>{it.ems_fee ? `${Number(it.ems_fee).toLocaleString()}원` : '-'}</td>
                    <td>{it.status === 'canceled' ? '취소' : it.is_test ? '테스트' : '접수'}</td>
                    <td>{it.created_by}</td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <a href={`/overseas-print/${it.id}`} className="btn btn-primary" target="_blank" rel="noreferrer">
                        출력서류
                      </a>
                      {it.status !== 'canceled' && (
                        <button type="button" className="btn btn-secondary" style={{ marginLeft: '0.35rem' }} onClick={() => handleCancel(it)}>
                          취소
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
