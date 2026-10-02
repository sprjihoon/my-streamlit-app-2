'use client';

import { useEffect, useState } from 'react';
import Alert from '@/components/Alert';
import Card from '@/components/Card';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import {
  cancelDomesticShipping,
  deleteDomesticShipping,
  listDomesticShipments,
  type DomesticShipment,
} from '@/lib/api';

function parseApiError(err: unknown): string {
  if (err instanceof Error) {
    try {
      const parsed = JSON.parse(err.message);
      if (typeof parsed?.detail === 'string') return parsed.detail;
    } catch {
      /* ignore */
    }
    return err.message;
  }
  return String(err);
}

function statusLabel(item: DomesticShipment) {
  if (item.status === 'canceled') return '취소';
  if (item.is_test) return '테스트';
  return '접수';
}

export default function DomesticShippingListPage() {
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [items, setItems] = useState<DomesticShipment[]>([]);
  const [isAdmin, setIsAdmin] = useState(false);

  async function load(tok: string) {
    const res = await listDomesticShipments(tok);
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
    load(stored).catch((err) => setError(parseApiError(err))).finally(() => setLoading(false));
  }, []);

  async function handleCancel(item: DomesticShipment) {
    if (!window.confirm(`송장 ${item.tracking_no || item.order_no} 접수를 취소할까요?\n실접수는 우체국 접수도 함께 취소합니다.`)) return;
    try {
      const result = await cancelDomesticShipping(token, item.id);
      setSuccess(result.message || '취소했습니다.');
      await load(token);
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  async function handleDelete(item: DomesticShipment) {
    const live = item.status !== 'canceled' && !item.is_test;
    const ask = live
      ? `송장 ${item.tracking_no || item.order_no} 접수를 우체국에서 취소한 뒤 목록에서 삭제할까요?`
      : `송장 ${item.tracking_no || item.order_no} 접수를 목록에서 삭제할까요?`;
    if (!window.confirm(ask)) return;
    try {
      const result = await deleteDomesticShipping(token, item.id);
      setSuccess(result.message || '삭제했습니다.');
      await load(token);
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  if (loading) return <Loading text="출고 목록을 불러오는 중..." />;

  return (
    <div>
      <PageHeader title="출고 목록" />
      {error && <Alert type="error">{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}
      <Card>
        <div style={{ marginBottom: 12 }}>
          <a href="/domestic-shipping" className="btn btn-primary">새 접수</a>
          <a href="/domestic-vendors" className="btn btn-secondary" style={{ marginLeft: 8 }}>업체 등록</a>
        </div>
        {items.length === 0 ? <p className="text-muted">접수 내역이 없습니다.</p> : (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>접수일</th><th>업체</th><th>수취인</th><th>송장번호</th><th>요금</th><th>상태</th><th>접수자</th><th>관리</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} style={{ cursor: 'pointer' }} onClick={() => { window.location.href = `/domestic-shipping-list/${item.id}`; }}>
                    <td>{(item.created_at || '').replace('T', ' ').slice(0, 16)}</td>
                    <td>{item.vendor_name}</td>
                    <td>{item.recipient_name}</td>
                    <td style={{ fontFamily: 'monospace' }}>{item.tracking_no || '-'}</td>
                    <td>{item.price || '-'}</td>
                    <td>{statusLabel(item)}</td>
                    <td>{item.created_by}</td>
                    <td style={{ whiteSpace: 'nowrap' }} onClick={(e) => e.stopPropagation()}>
                      <a className="btn btn-secondary" href={`/domestic-print/${item.id}`} target="_blank" rel="noreferrer">송장</a>
                      {item.status !== 'canceled' && (
                        <button type="button" className="btn btn-primary" style={{ marginLeft: 6 }} onClick={() => void handleCancel(item)}>접수 취소</button>
                      )}
                      {isAdmin && (
                        <button type="button" className="btn btn-secondary" style={{ marginLeft: 6 }} onClick={() => void handleDelete(item)}>삭제</button>
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
