'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Card } from '@/components/Card';
import { Alert } from '@/components/Alert';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const SAVED_ID_KEY = 'saved_username';

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 페이지 로드 시 저장된 아이디 불러오기
  useEffect(() => {
    const saved = localStorage.getItem(SAVED_ID_KEY);
    if (saved) {
      setUsername(saved);
      setRememberMe(true);
    }
  }, []);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();

    // 아이디 저장 처리
    if (rememberMe) {
      localStorage.setItem(SAVED_ID_KEY, username);
    } else {
      localStorage.removeItem(SAVED_ID_KEY);
    }
    
    if (!username.trim() || !password.trim()) {
      setError('아이디와 비밀번호를 입력하세요.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || '로그인 실패');
      }

      // 로컬 스토리지에 저장
      localStorage.setItem('token', data.token);
      localStorage.setItem('user', JSON.stringify(data.user));
      localStorage.setItem('isAdmin', data.user.is_admin ? 'true' : 'false');
      
      // 최초 로그인 비밀번호 변경 필요 여부 저장
      if (data.must_change_password) {
        localStorage.setItem('must_change_password', 'true');
      } else {
        localStorage.removeItem('must_change_password');
      }

      // 메인 페이지로 이동
      router.push('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : '로그인 실패');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        padding: '1rem',
      }}
    >
      <Card style={{ width: '100%', maxWidth: '400px', padding: '2rem' }}>
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <h1 style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>📦 인보이스 관리 시스템</h1>
          <p style={{ color: '#666' }}>로그인이 필요합니다</p>
        </div>

        {error && <Alert type="error" message={error} onClose={() => setError(null)} />}

        <form onSubmit={handleLogin}>
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
              아이디
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="아이디 입력"
              autoComplete="username"
              style={{
                width: '100%',
                padding: '0.75rem',
                border: '1px solid #ddd',
                borderRadius: '4px',
                fontSize: '1rem',
              }}
            />
          </div>

          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
              비밀번호
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="비밀번호 입력"
              autoComplete="current-password"
              style={{
                width: '100%',
                padding: '0.75rem',
                border: '1px solid #ddd',
                borderRadius: '4px',
                fontSize: '1rem',
              }}
            />
          </div>

          {/* 아이디 저장 */}
          <div style={{ marginBottom: '1.5rem' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', userSelect: 'none' }}>
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                style={{ width: '16px', height: '16px', cursor: 'pointer', accentColor: '#4CAF50' }}
              />
              <span style={{ fontSize: '0.875rem', color: '#555' }}>아이디 저장</span>
            </label>
          </div>

          <button
            type="submit"
            disabled={loading}
            style={{
              width: '100%',
              padding: '0.75rem',
              backgroundColor: loading ? '#ccc' : '#4CAF50',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              fontSize: '1rem',
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            {loading ? '로그인 중...' : '로그인'}
          </button>
        </form>

      </Card>
    </div>
  );
}

