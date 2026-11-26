'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { A4Preview } from '../../a4-preview';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function EmploymentContractPrintPage() {
  const { id } = useParams<{ id: string }>();
  const [pages, setPages] = useState<string[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    const token = localStorage.getItem('token') || '';
    if (!token) {
      setError('로그인이 필요합니다.');
      return;
    }
    try {
      const user = JSON.parse(localStorage.getItem('user') || '{}');
      if (!user.is_admin) {
        setError('완료된 근로계약서는 관리자만 확인할 수 있습니다.');
        return;
      }
    } catch {
      setError('완료된 근로계약서는 관리자만 확인할 수 있습니다.');
      return;
    }
    fetch(`${API}/employment-contracts/${id}/pages?token=${encodeURIComponent(token)}`)
      .then(async (res) => {
        if (!res.ok) {
          const text = await res.text();
          throw new Error(text || '계약서를 불러오지 못했습니다.');
        }
        return res.json();
      })
      .then((data) => setPages(data.pages || []))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : '계약서를 불러오지 못했습니다.'));
  }, [id]);

  if (error) {
    return <p style={{ padding: '2rem', textAlign: 'center' }}>{error}</p>;
  }
  if (pages.length === 0) {
    return <p style={{ padding: '2rem', textAlign: 'center' }}>A4 미리보기를 준비하는 중...</p>;
  }
  return <A4Preview pages={pages} />;
}
