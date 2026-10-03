'use client';

import { useEffect, useRef, useState } from 'react';
import { useParams } from 'next/navigation';
import Alert from '@/components/Alert';
import Card from '@/components/Card';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import { ConfirmDialog } from '@/components/domestic/ConfirmDialog';
import { CopyButton } from '@/components/domestic/CopyButton';
import {
  cancelDomesticShipping,
  deleteDomesticShipping,
  getDomesticShipment,
  type DomesticShipment,
} from '@/lib/api';
import { classifyDomesticError, domesticStatusLabel, listReturnHref } from '@/lib/domestic-form';

type Pending = 'cancel' | 'delete' | null;

function partyLine(name: string, phone: string, zip: string, addr1: string, addr2: string) {
  return (
    <>
      {name} · {phone}<br />{zip} {addr1} {addr2}
    </>
  );
}

export default function DomesticShippingDetailPage() {
  const { id } = useParams<{ id: string }>();
  const shipmentId = Number(id);
  const [token, setToken] = useState('');
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [item, setItem] = useState<DomesticShipment | null>(null);
  const [listHref, setListHref] = useState('/domestic-shipping-list');
  const [pending, setPending] = useState<Pending>(null);
  const [acting, setActing] = useState(false);
  const actingRef = useRef(false);

  useEffect(() => {
    setListHref(listReturnHref(window.location.search));
    const stored = localStorage.getItem('token') || '';
    setToken(stored);
    setIsAdmin(localStorage.getItem('isAdmin') === 'true');
    if (!stored) {
      setError('로그인이 필요합니다.');
      setLoading(false);
      return;
    }
    if (!Number.isInteger(shipmentId) || shipmentId <= 0) {
      setError('접수를 찾지 못했습니다.');
      setLoading(false);
      return;
    }
    getDomesticShipment(stored, shipmentId)
      .then((next) => {
        if (next.id !== shipmentId) {
          setError('접수를 찾지 못했습니다.');
          return;
        }
        setItem(next);
      })
      .catch((err) => setError(classifyDomesticError(err, 'shipment').message))
      .finally(() => setLoading(false));
  }, [shipmentId]);

  function dismissPending() {
    if (actingRef.current) return;
    setPending(null);
  }

  async function confirmPending() {
    if (!item || !pending || actingRef.current) return;
    actingRef.current = true;
    setActing(true);
    setError(null);
    setSuccess(null);
    try {
      if (pending === 'delete') {
        await deleteDomesticShipping(token, item.id);
        window.location.href = listHref;
        return;
      }
      const result = await cancelDomesticShipping(token, item.id);
      const next = await getDomesticShipment(token, item.id);
      if (next.id === item.id) setItem(next);
      setSuccess(result.message || '취소했습니다.');
      setPending(null);
    } catch (err) {
      setError(classifyDomesticError(err, 'shipment').message);
      setPending(null);
    } finally {
      actingRef.current = false;
      setActing(false);
    }
  }

  if (loading) return <Loading text="접수 상세를 불러오는 중..." />;
  if (!item) {
    return (
      <div className="domestic-page">
        <PageHeader title="국내 출고 상세" subtitle="접수를 찾지 못했습니다." />
        {error ? <Alert type="error">{error}</Alert> : null}
        <a className="btn btn-secondary" href={listHref}>목록으로</a>
      </div>
    );
  }

  const no = item.tracking_no || item.order_no;
  const live = item.status !== 'canceled' && !item.is_test;
  const printHref = item.id === shipmentId ? `/domestic-print/${item.id}` : '';

  return (
    <div className="domestic-page domestic-form">
      <PageHeader title={item.recipient_name || '출고 상세'} subtitle={`${no} · ${domesticStatusLabel(item)}`} />
      {error ? <Alert type="error">{error}</Alert> : null}
      {success ? <Alert type="success">{success}</Alert> : null}
      <div className="domestic-actions">
        <a href={listHref} className="btn btn-secondary">목록으로</a>
        {printHref ? (
          <a href={printHref} className="btn btn-primary" target="_blank" rel="noreferrer">출력</a>
        ) : null}
        {item.status !== 'canceled' ? (
          <button type="button" className="btn btn-warning" onClick={() => setPending('cancel')}>접수 취소</button>
        ) : null}
        {isAdmin ? (
          <button type="button" className="btn btn-danger" onClick={() => setPending('delete')}>삭제</button>
        ) : null}
      </div>
      <Card>
        <dl className="domestic-facts">
          <dt>받는 사람</dt>
          <dd>{partyLine(item.recipient_name, item.recipient_phone, item.recipient_zip, item.recipient_addr1, item.recipient_addr2)}</dd>
          <dt>송장번호</dt>
          <dd><CopyButton value={item.tracking_no || ''} /></dd>
          <dt>접수번호</dt>
          <dd className="domestic-mono">{item.order_no || '-'}</dd>
          <dt>업체</dt>
          <dd>{item.vendor_name}</dd>
          <dt>상태</dt>
          <dd>{domesticStatusLabel(item)}</dd>
          <dt>접수일</dt>
          <dd>{(item.created_at || '').replace('T', ' ').slice(0, 16) || '-'}</dd>
          <dt>상품</dt>
          <dd>{item.goods_name} {item.goods_qty || 1}개 · {item.box_size}</dd>
          {item.notes ? (<><dt>배송메시지</dt><dd>{item.notes}</dd></>) : null}
          {item.price ? (<><dt>요금</dt><dd>{item.price}</dd></>) : null}
          {item.post_office ? (<><dt>접수우체국</dt><dd>{item.post_office}</dd></>) : null}
          <dt>공급지</dt>
          <dd>{item.office_ser}</dd>
        </dl>
      </Card>
      <Card>
        <dl className="domestic-facts">
          <dt>송장</dt>
          <dd>{partyLine(item.print_sender_name, item.print_sender_phone, item.print_sender_zip, item.print_sender_addr1, item.print_sender_addr2)}</dd>
          <dt>우체국</dt>
          <dd>{partyLine(item.api_sender_name, item.api_sender_phone, item.api_sender_zip, item.api_sender_addr1, item.api_sender_addr2)}</dd>
          {item.canceled_at ? (<><dt>취소</dt><dd>{item.canceled_at.replace('T', ' ')} {item.canceled_by || ''}</dd></>) : null}
        </dl>
      </Card>

      <ConfirmDialog
        open={pending !== null}
        title={pending === 'delete' ? '목록에서 삭제' : '접수 취소'}
        description={
          pending === 'delete'
            ? (live
              ? `송장 ${no} 접수를 우체국에서 취소한 뒤 목록에서 삭제할까요?`
              : `송장 ${no} 접수를 목록에서 삭제할까요?`)
            : (item.is_test
              ? `송장 ${no} 테스트 접수를 취소할까요? 우체국에는 취소 요청을 보내지 않습니다.`
              : `송장 ${no} 접수를 취소할까요? 실접수는 우체국 접수도 함께 취소합니다.`)
        }
        confirmLabel={pending === 'delete' ? '삭제' : '접수 취소'}
        confirmClass={pending === 'delete' ? 'btn btn-danger' : 'btn btn-warning'}
        busy={acting}
        busyLabel="처리 중..."
        onDismiss={dismissPending}
        onConfirm={() => void confirmPending()}
      />
    </div>
  );
}
