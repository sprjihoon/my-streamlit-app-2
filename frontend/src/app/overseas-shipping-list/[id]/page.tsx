'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Card from '@/components/Card';
import Alert from '@/components/Alert';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import {
  cancelOverseasShipping,
  getOverseasShipment,
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

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '0.55rem 0.7rem',
  border: '1px solid var(--border)',
  borderRadius: '8px',
  fontFamily: 'inherit',
  fontSize: '0.9rem',
  background: '#f8fafc',
};

function Field({ label, value }: { label: string; value: string }) {
  return (
    <label>
      {label}
      <input style={inputStyle} value={value} readOnly />
    </label>
  );
}

export default function OverseasShippingDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [item, setItem] = useState<OverseasShippingItem | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem('token') || '';
    setToken(stored);
    const shipmentId = Number(id);
    if (!stored) {
      setError('로그인이 필요합니다.');
      setLoading(false);
      return;
    }
    if (!shipmentId) {
      setError('접수 번호가 없습니다.');
      setLoading(false);
      return;
    }
    (async () => {
      try {
        setItem(await getOverseasShipment(stored, shipmentId));
      } catch (err) {
        setError(parseApiError(err));
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  async function handleCancel() {
    if (!item || !token) return;
    if (!window.confirm(`등기번호 ${item.tracking_no || item.order_no} 접수를 취소할까요?`)) return;
    setError(null);
    setSuccess(null);
    try {
      const result = await cancelOverseasShipping(token, item.id);
      setSuccess(result.message || '취소했습니다.');
      setItem(await getOverseasShipment(token, item.id));
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  if (loading) return <Loading text="접수 상세 로딩 중..." />;

  const status = item?.status === 'canceled' ? '취소' : item?.is_test ? '테스트' : '접수';
  const senderAddr = [item?.sender_addr1, item?.sender_addr2, item?.sender_addr3].filter(Boolean).join(', ');

  return (
    <div className="overseas-page">
      <PageHeader
        title="해외배송 접수 상세"
        subtitle={item ? `${item.order_no} · ${(item.created_at || '').replace('T', ' ').slice(0, 16)}` : '접수한 입력값을 그대로 봅니다.'}
      />
      {error && <Alert type="error">{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}
      {!item ? (
        <Card title="접수">
          <a href="/overseas-shipping-list" className="btn btn-secondary">접수목록</a>
        </Card>
      ) : (
        <>
          <div style={{ marginBottom: '1rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <a href="/overseas-shipping-list" className="btn btn-secondary">접수목록</a>
            <a href={`/overseas-print/${item.id}`} className="btn btn-primary" target="_blank" rel="noreferrer">출력서류</a>
            {item.status !== 'canceled' && (
              <button type="button" className="btn btn-secondary" onClick={handleCancel}>취소</button>
            )}
          </div>
          <Card title={`${METHOD_LABEL[item.shipping_method] || item.shipping_method} · ${item.contents_label || '화물'} · ${status}`}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem' }}>
              <Field label="등기번호" value={item.tracking_no || '-'} />
              <Field label="요금" value={item.ems_fee ? `${Number(item.ems_fee).toLocaleString()}원` : '-'} />
              <Field label="접수자" value={item.created_by || ''} />
              <Field label="우체국" value={item.post_office || ''} />
            </div>
          </Card>
          <Card title="발송인">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem' }}>
              <Field label="이름" value={item.sender_name || ''} />
              <Field label="우편번호" value={item.sender_zipcode || ''} />
              <Field label="전화" value={item.sender_tel || ''} />
              <Field label="주소" value={senderAddr} />
            </div>
          </Card>
          <Card title="수취인">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem' }}>
              <Field label="이름" value={item.recipient_name || ''} />
              <Field label="연락처" value={item.recipient_phone || ''} />
              <Field label="이메일" value={item.recipient_email || ''} />
              <Field label="국가" value={item.countrycd || ''} />
              <Field label="우편번호" value={item.recipient_zip || ''} />
              <Field label="주/도" value={item.recipient_addr1 || ''} />
              <Field label="시/군" value={item.recipient_addr2 || ''} />
              <Field label="상세주소" value={item.recipient_addr3 || ''} />
            </div>
          </Card>
          <Card title="화물">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem' }}>
              <Field label="총중량 (g)" value={String(item.totweight || '')} />
              <Field label="가로 (cm)" value={item.contents_type === 'document' ? '' : String(item.boxlength || '')} />
              <Field label="세로 (cm)" value={item.contents_type === 'document' ? '' : String(item.boxwidth || '')} />
              <Field label="높이 (cm)" value={item.contents_type === 'document' ? '' : String(item.boxheight || '')} />
              <Field label="메모" value={item.notes || ''} />
            </div>
          </Card>
          <Card title="세관 인보이스">
            {(item.items || []).length === 0 ? (
              <p className="text-muted">품목이 없습니다.</p>
            ) : (
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>제품명</th>
                      <th>품목</th>
                      <th>수량</th>
                      <th>단가 USD</th>
                      <th>HS코드</th>
                      <th>원산지</th>
                    </tr>
                  </thead>
                  <tbody>
                    {item.items.map((row, i) => (
                      <tr key={i}>
                        <td>{row.product_name || '-'}</td>
                        <td>{row.name_en || '-'}</td>
                        <td>{row.quantity}</td>
                        <td>{row.unit_price_usd}</td>
                        <td>{row.hs_code || '-'}</td>
                        <td>{row.origin_country || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
