'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { domesticLabelPdfUrl, getDomesticShipment, type DomesticShipment } from '@/lib/api';

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

export default function DomesticPrintPage() {
  const { id } = useParams<{ id: string }>();
  const [item, setItem] = useState<DomesticShipment | null>(null);
  const [pdfUrl, setPdfUrl] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('token') || '';
    const shipmentId = Number(id);
    if (!token || !shipmentId) {
      setError(token ? '접수 번호가 없습니다.' : '로그인이 필요합니다.');
      setLoading(false);
      return;
    }
    setPdfUrl(domesticLabelPdfUrl(token, shipmentId));
    getDomesticShipment(token, shipmentId)
      .then(setItem)
      .catch((err) => setError(parseApiError(err)))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <p style={{ padding: '2rem', textAlign: 'center' }}>송장을 불러오는 중...</p>;
  if (error || !item || !pdfUrl) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <p style={{ color: '#b91c1c' }}>{error || '송장을 찾을 수 없습니다.'}</p>
        <a href="/domestic-shipping-list">← 접수목록</a>
      </div>
    );
  }

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <div style={{ background: '#111827', color: '#d1d5db', padding: '8px 16px', fontSize: 13 }}>
        <a href="/domestic-shipping-list" style={{ color: '#d1d5db' }}>← 접수목록</a>
        <span style={{ marginLeft: 12 }}>
          {item.tracking_no || item.order_no} · 송장 보내는 사람 {item.print_sender_name}. 우체국 답안지 반영 전입니다.
        </span>
      </div>
      <iframe title="국내 출고 송장" src={pdfUrl} style={{ flex: 1, width: '100%', border: 'none', background: '#fff' }} />
    </div>
  );
}
