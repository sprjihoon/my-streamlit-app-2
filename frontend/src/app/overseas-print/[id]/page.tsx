'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import {
  getOverseasShippingLabel,
  overseasLabelPdfUrl,
  type OverseasLabelData,
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

export default function OverseasPrintPage() {
  const { id } = useParams<{ id: string }>();
  const [label, setLabel] = useState<OverseasLabelData | null>(null);
  const [htmlUrl, setHtmlUrl] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('token') || '';
    const shipmentId = Number(id);
    if (!token) {
      setError('로그인이 필요합니다.');
      setLoading(false);
      return;
    }
    if (!shipmentId) {
      setError('접수 번호가 없습니다.');
      setLoading(false);
      return;
    }
    setHtmlUrl(overseasLabelPdfUrl(token, shipmentId));
    (async () => {
      try {
        const res = await getOverseasShippingLabel(token, shipmentId);
        setLabel(res.label);
      } catch (err) {
        setError(parseApiError(err));
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  if (loading) {
    return <p style={{ padding: '2rem', textAlign: 'center' }}>출력서류를 불러오는 중...</p>;
  }
  if (error || !label || !htmlUrl) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <p style={{ color: '#b91c1c' }}>{error || '출력서류를 찾을 수 없습니다.'}</p>
        <a href="/overseas-shipping-list">← 접수목록</a>
      </div>
    );
  }

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <div style={{ background: '#111827', color: '#d1d5db', padding: '8px 16px', fontSize: 13 }}>
        <a href="/overseas-shipping-list" style={{ color: '#d1d5db' }}>← 접수목록</a>
        <span style={{ marginLeft: 12 }}>{label.order_no} · 1장 주소기표지 · 2·3장 세관신고서. 인쇄는 서류 화면의 인쇄 버튼을 누릅니다.</span>
      </div>
      <iframe title="해외배송 출력서류" src={htmlUrl} style={{ flex: 1, width: '100%', border: 'none', background: '#fff' }} />
    </div>
  );
}
