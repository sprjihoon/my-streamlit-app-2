'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Alert from '@/components/Alert';
import Card from '@/components/Card';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import {
  cancelDomesticShipping,
  deleteDomesticShipping,
  getDomesticShipment,
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

export default function DomesticShippingDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [token, setToken] = useState('');
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [item, setItem] = useState<DomesticShipment | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem('token') || '';
    setToken(stored);
    setIsAdmin(localStorage.getItem('isAdmin') === 'true');
    if (!stored) {
      setError('로그인이 필요합니다.');
      setLoading(false);
      return;
    }
    getDomesticShipment(stored, Number(id))
      .then(setItem)
      .catch((err) => setError(parseApiError(err)))
      .finally(() => setLoading(false));
  }, [id]);

  async function handleCancel() {
    if (!item || !window.confirm(`송장 ${item.tracking_no || item.order_no} 접수를 취소할까요?`)) return;
    try {
      const result = await cancelDomesticShipping(token, item.id);
      setSuccess(result.message || '취소했습니다.');
      setItem(await getDomesticShipment(token, item.id));
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  async function handleDelete() {
    if (!item) return;
    if (!window.confirm(`송장 ${item.tracking_no || item.order_no} 접수를 목록에서 삭제할까요?`)) return;
    try {
      await deleteDomesticShipping(token, item.id);
      window.location.href = '/domestic-shipping-list';
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  if (loading) return <Loading text="접수 상세를 불러오는 중..." />;
  if (!item) {
    return (
      <div>
        <PageHeader title="국내 출고 상세" subtitle="접수를 찾지 못했습니다." />
        {error && <Alert type="error">{error}</Alert>}
      </div>
    );
  }
  const status = item.status === 'canceled' ? '취소' : item.is_test ? '테스트' : '접수';

  return (
    <div className="domestic-form">
      <PageHeader title="출고 상세" subtitle={`${item.tracking_no || item.order_no} · ${status}`} />
      {error && <Alert type="error">{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}
      <div style={{ marginBottom: 12 }}>
        <a href="/domestic-shipping-list" className="btn btn-secondary">목록</a>
        <a href={`/domestic-print/${item.id}`} className="btn btn-primary" style={{ marginLeft: 8 }} target="_blank" rel="noreferrer">송장</a>
        {item.status !== 'canceled' && (
          <button type="button" className="btn btn-secondary" style={{ marginLeft: 8 }} onClick={() => void handleCancel()}>취소</button>
        )}
        {isAdmin && (
          <button type="button" className="btn btn-secondary" style={{ marginLeft: 8 }} onClick={() => void handleDelete()}>삭제</button>
        )}
      </div>
      <Card>
        <dl className="domestic-facts">
          <dt>업체</dt><dd>{item.vendor_name}</dd>
          <dt>송장번호</dt><dd>{item.tracking_no || '-'}</dd>
          <dt>공급지</dt><dd>{item.office_ser}</dd>
          <dt>상품</dt><dd>{item.goods_name} {item.goods_qty || 1}개 · {item.box_size}</dd>
          <dt>우체국</dt><dd>{item.api_sender_name} · {item.api_sender_phone}<br />{item.api_sender_zip} {item.api_sender_addr1} {item.api_sender_addr2}</dd>
          <dt>송장</dt><dd>{item.print_sender_name} · {item.print_sender_phone}<br />{item.print_sender_zip} {item.print_sender_addr1} {item.print_sender_addr2}</dd>
          <dt>받는 사람</dt><dd>{item.recipient_name} · {item.recipient_phone}<br />{item.recipient_zip} {item.recipient_addr1} {item.recipient_addr2}</dd>
        </dl>
      </Card>
    </div>
  );
}
