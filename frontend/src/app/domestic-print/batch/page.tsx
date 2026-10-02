'use client';

import { useEffect, useState } from 'react';
import { domesticLabelsPdfUrl, getDomesticShipment, type DomesticShipment } from '@/lib/api';

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

export default function DomesticBatchPrintPage() {
  const [items, setItems] = useState<DomesticShipment[]>([]);
  const [pdfUrl, setPdfUrl] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('token') || '';
    const ids = new URLSearchParams(window.location.search).get('ids') || '';
    const shipmentIds = ids.split(',').map((part) => Number(part)).filter((id) => id > 0);
    if (!token || shipmentIds.length === 0) {
      setError(token ? '송장 번호가 없습니다.' : '로그인이 필요합니다.');
      setLoading(false);
      return;
    }
    setPdfUrl(domesticLabelsPdfUrl(token, shipmentIds));
    Promise.all(shipmentIds.map((id) => getDomesticShipment(token, id)))
      .then(setItems)
      .catch((err) => setError(parseApiError(err)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p style={{ padding: '2rem', textAlign: 'center' }}>송장을 불러오는 중...</p>;
  if (error || items.length === 0 || !pdfUrl) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <p style={{ color: '#b91c1c' }}>{error || '송장을 찾을 수 없습니다.'}</p>
        <a href="/domestic-shipping-list">← 접수목록</a>
      </div>
    );
  }

  const summary = items.map((item) => item.tracking_no || item.order_no).join(', ');

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <div style={{ background: '#111827', color: '#d1d5db', padding: '8px 16px', fontSize: 13 }}>
        <a href="/domestic-shipping-list" style={{ color: '#d1d5db' }}>← 접수목록</a>
        <span style={{ marginLeft: 12 }}>
          {items.length}장 · {summary}
        </span>
      </div>
      <iframe title="국내 출고 송장" src={pdfUrl} style={{ flex: 1, width: '100%', border: 'none', background: '#fff' }} />
    </div>
  );
}
