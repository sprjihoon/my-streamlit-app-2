'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Alert } from '@/components/Alert';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';

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
    <div className="login-shell">
      <form className="login-panel" onSubmit={handleLogin}>
        <div className="login-brand">
          <div className="sidebar-mark" aria-hidden>T</div>
          <div className="login-brand-copy">
            <h1>틸리언</h1>
            <p>그룹웨어에 로그인합니다</p>
          </div>
        </div>

        {error && <Alert type="error" message={error} onClose={() => setError(null)} />}

        <Field label="아이디" required>
          <Input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="아이디 입력"
            autoComplete="username"
          />
        </Field>
        <Field label="비밀번호" required>
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="비밀번호 입력"
            autoComplete="current-password"
          />
        </Field>
        <label className="login-remember">
          <input
            type="checkbox"
            checked={rememberMe}
            onChange={(e) => setRememberMe(e.target.checked)}
          />
          아이디 저장
        </label>
        <Button type="submit" variant="primary" disabled={loading} className="tw-w-full">
          {loading ? '로그인 중...' : '로그인'}
        </Button>
      </form>
    </div>
  );
}

