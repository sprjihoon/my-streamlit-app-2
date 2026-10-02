'use client';

import { useState } from 'react';
import { KeyRound } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function MustChangePasswordModal({ onSuccess }: { onSuccess: () => void }) {
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!newPw || newPw.length < 4) return setError('비밀번호는 4자 이상이어야 합니다.');
    if (newPw !== confirmPw) return setError('비밀번호가 일치하지 않습니다.');
    if (newPw === '123456') return setError('초기 비밀번호와 다른 비밀번호를 사용하세요.');
    setLoading(true);
    setError('');
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_URL}/auth/change-password?token=${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: '123456', new_password: newPw }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '변경 실패');
      localStorage.removeItem('must_change_password');
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : '변경 실패');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999 }}>
      <div style={{ backgroundColor: 'white', borderRadius: '12px', padding: '2rem', width: '380px', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }}>
        <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
          <div style={{ marginBottom: '0.75rem', display: 'flex', justifyContent: 'center' }}>
            <div style={{ width: '52px', height: '52px', borderRadius: '50%', background: '#eef2ff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <KeyRound size={24} style={{ color: '#4361ee' }} />
            </div>
          </div>
          <h3 style={{ margin: 0, marginBottom: '0.5rem' }}>비밀번호 변경 필요</h3>
          <p style={{ margin: 0, fontSize: '0.875rem', color: '#6c757d' }}>
            초기 비밀번호(123456)를 변경해야 합니다.<br />
            새 비밀번호를 설정해주세요.
          </p>
        </div>
        {error && (
          <div style={{ padding: '0.5rem', marginBottom: '1rem', backgroundColor: '#f8d7da', color: '#842029', borderRadius: '4px', fontSize: '0.875rem' }}>
            {error}
          </div>
        )}
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', fontWeight: 500, marginBottom: '0.25rem', fontSize: '0.875rem' }}>새 비밀번호</label>
            <input type="password" value={newPw} onChange={e => setNewPw(e.target.value)}
              placeholder="새 비밀번호 (4자 이상)"
              style={{ width: '100%', padding: '0.6rem', border: '1px solid #dee2e6', borderRadius: '4px' }} />
          </div>
          <div style={{ marginBottom: '1.5rem' }}>
            <label style={{ display: 'block', fontWeight: 500, marginBottom: '0.25rem', fontSize: '0.875rem' }}>새 비밀번호 확인</label>
            <input type="password" value={confirmPw} onChange={e => setConfirmPw(e.target.value)}
              placeholder="비밀번호 재입력"
              style={{ width: '100%', padding: '0.6rem', border: '1px solid #dee2e6', borderRadius: '4px' }} />
          </div>
          <button type="submit" disabled={loading}
            style={{ width: '100%', padding: '0.75rem', backgroundColor: loading ? '#ccc' : '#0d6efd', color: 'white', border: 'none', borderRadius: '6px', fontWeight: 600, cursor: 'pointer' }}>
            {loading ? '변경 중...' : '비밀번호 변경'}
          </button>
        </form>
      </div>
    </div>
  );
}
