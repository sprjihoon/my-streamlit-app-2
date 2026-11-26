'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function EmploymentContractPrintPage() {
  const { id } = useParams<{ id: string }>();
  const [pdfUrl, setPdfUrl] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    const token = localStorage.getItem('token') || '';
    if (!token) {
      setError('로그인이 필요합니다.');
      return;
    }
    setPdfUrl(`${API}/employment-contracts/${id}/pdf?token=${encodeURIComponent(token)}`);
  }, [id]);

  if (error) {
    return <p style={{ padding: '2rem', textAlign: 'center' }}>{error}</p>;
  }
  if (!pdfUrl) {
    return <p style={{ padding: '2rem', textAlign: 'center' }}>계약서를 불러오는 중...</p>;
  }

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <div style={{ background: '#111827', color: '#e5e7eb', padding: '8px 16px', fontSize: 13 }}>
        <a href="/employment-contracts" style={{ color: '#e5e7eb' }}>← 근로계약</a>
        <span style={{ marginLeft: 12 }}>PDF 화면의 인쇄로 출력할 수 있습니다.</span>
      </div>
      <iframe title="근로계약서" src={pdfUrl} style={{ flex: 1, width: '100%', border: 'none', background: '#fff' }} />
    </div>
  );
}
