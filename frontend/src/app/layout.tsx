'use client';

import './globals.css';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface User {
  user_id: number;
  username: string;
  nickname: string;
  is_admin: boolean;
}

/**
 * 네비게이션 링크 (Streamlit pages/ 구조와 동일)
 */
const NAV_ITEMS = [
  { href: '/', label: '🏠 대시보드' },
  { href: '/upload', label: '📤 데이터 업로드' },
  { href: '/mapping', label: '🔗 업체 매핑 관리' },
  { href: '/vendors', label: '📋 매핑 리스트' },
  { href: '/rates', label: '💰 요금표 관리' },
  { href: '/invoice', label: '📊 인보이스 계산' },
  { href: '/invoice-list', label: '📜 인보이스 목록' },
  { href: '/insights', label: '📈 데이터 인사이트' },
];

const ADMIN_NAV_ITEMS = [
  { href: '/users', label: '👥 사용자 관리' },
  { href: '/logs', label: '📝 활동 로그' },
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  
  // 비밀번호 변경 모달
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null);
  const [changingPassword, setChangingPassword] = useState(false);

  // 로그인 페이지는 레이아웃 적용 안함
  const isLoginPage = pathname === '/login';

  useEffect(() => {
    if (isLoginPage) {
      setLoading(false);
      return;
    }
    checkAuth();
  }, [pathname]);

  async function checkAuth() {
    const token = localStorage.getItem('token');
    const storedUser = localStorage.getItem('user');

    if (!token || !storedUser) {
      router.push('/login');
      return;
    }

    try {
      // 토큰 유효성 확인
      const res = await fetch(`${API_URL}/auth/me?token=${token}`);
      if (!res.ok) {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        router.push('/login');
        return;
      }

      const userData = await res.json();
      setUser(userData);
    } catch {
      // API 연결 실패 시 저장된 사용자 정보 사용
      try {
        setUser(JSON.parse(storedUser));
      } catch {
        router.push('/login');
      }
    } finally {
      setLoading(false);
    }
  }

  function handleLogout() {
    const token = localStorage.getItem('token');
    if (token) {
      fetch(`${API_URL}/auth/logout?token=${token}`, { method: 'POST' }).catch(() => {});
    }
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    router.push('/login');
  }

  async function handleChangePassword() {
    setPasswordError(null);
    setPasswordSuccess(null);

    if (!currentPassword || !newPassword || !confirmPassword) {
      setPasswordError('모든 필드를 입력하세요.');
      return;
    }

    if (newPassword !== confirmPassword) {
      setPasswordError('새 비밀번호가 일치하지 않습니다.');
      return;
    }

    if (newPassword.length < 4) {
      setPasswordError('비밀번호는 4자 이상이어야 합니다.');
      return;
    }

    const token = localStorage.getItem('token');
    if (!token) {
      setPasswordError('로그인이 필요합니다.');
      return;
    }

    setChangingPassword(true);

    try {
      const res = await fetch(`${API_URL}/auth/change-password?token=${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || '비밀번호 변경 실패');
      }

      setPasswordSuccess('비밀번호가 변경되었습니다.');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      
      setTimeout(() => {
        setShowPasswordModal(false);
        setPasswordSuccess(null);
      }, 1500);
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : '비밀번호 변경 실패');
    } finally {
      setChangingPassword(false);
    }
  }

  // 로그인 페이지
  if (isLoginPage) {
    return (
      <html lang="ko">
        <head>
          <title>로그인 - 청구서 관리 시스템</title>
          <meta name="viewport" content="width=device-width, initial-scale=1" />
        </head>
        <body>{children}</body>
      </html>
    );
  }

  // 로딩 중
  if (loading) {
    return (
      <html lang="ko">
        <head>
          <title>청구서 관리 시스템</title>
          <meta name="viewport" content="width=device-width, initial-scale=1" />
        </head>
        <body>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
            <p>로딩 중...</p>
          </div>
        </body>
      </html>
    );
  }

  return (
    <html lang="ko">
      <head>
        <title>청구서 관리 시스템</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body>
        <div className="layout">
          {/* 사이드바 (Streamlit 스타일) */}
          <aside className="sidebar">
            <h1>📋 청구서 시스템</h1>
            
            {/* 사용자 정보 - 항상 표시 */}
            {user ? (
              <div
                style={{
                  padding: '0.75rem',
                  marginBottom: '1rem',
                  backgroundColor: '#f0f4f8',
                  borderRadius: '4px',
                  border: '1px solid #dee2e6',
                }}
              >
                <div style={{ fontWeight: 'bold', marginBottom: '0.25rem', color: '#212529' }}>
                  👤 {user.nickname}
                </div>
                <div style={{ fontSize: '0.75rem', color: '#6c757d' }}>
                  {user.is_admin ? '🔐 관리자' : '👤 일반 사용자'}
                </div>
                <div style={{ display: 'flex', gap: '0.25rem', marginTop: '0.5rem' }}>
                  <button
                    onClick={() => {
                      setShowPasswordModal(true);
                      setPasswordError(null);
                      setPasswordSuccess(null);
                      setCurrentPassword('');
                      setNewPassword('');
                      setConfirmPassword('');
                    }}
                    style={{
                      flex: 1,
                      padding: '0.25rem 0.5rem',
                      fontSize: '0.75rem',
                      backgroundColor: '#0d6efd',
                      color: 'white',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: 'pointer',
                    }}
                  >
                    비번변경
                  </button>
                  <button
                    onClick={handleLogout}
                    style={{
                      flex: 1,
                      padding: '0.25rem 0.5rem',
                      fontSize: '0.75rem',
                      backgroundColor: '#6c757d',
                      color: 'white',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: 'pointer',
                    }}
                  >
                    로그아웃
                  </button>
                </div>
              </div>
            ) : (
              <div
                style={{
                  padding: '0.75rem',
                  marginBottom: '1rem',
                  backgroundColor: '#f0f4f8',
                  borderRadius: '4px',
                  border: '1px solid #dee2e6',
                }}
              >
                <button
                  onClick={handleLogout}
                  style={{
                    width: '100%',
                    padding: '0.5rem',
                    fontSize: '0.875rem',
                    backgroundColor: '#6c757d',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                  }}
                >
                  🔓 로그아웃
                </button>
              </div>
            )}
            
            <nav>
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={pathname === item.href ? 'active' : ''}
                >
                  {item.label}
                </Link>
              ))}
              
              {/* 관리자 전용 메뉴 */}
              {user?.is_admin && (
                <>
                  <div style={{ borderTop: '1px solid rgba(255,255,255,0.2)', margin: '0.5rem 0' }} />
                  {ADMIN_NAV_ITEMS.map((item) => (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={pathname === item.href ? 'active' : ''}
                    >
                      {item.label}
                    </Link>
                  ))}
                </>
              )}
            </nav>
          </aside>

          {/* 메인 콘텐츠 */}
          <main className="main-content">{children}</main>
        </div>

        {/* 비밀번호 변경 모달 */}
        {showPasswordModal && (
          <div
            style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: 'rgba(0,0,0,0.5)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 1000,
            }}
            onClick={() => setShowPasswordModal(false)}
          >
            <div
              style={{
                backgroundColor: 'white',
                borderRadius: '8px',
                padding: '2rem',
                width: '350px',
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <h3 style={{ marginBottom: '1rem' }}>🔑 비밀번호 변경</h3>

              {passwordError && (
                <div style={{ padding: '0.5rem', marginBottom: '1rem', backgroundColor: '#ffebee', color: '#c62828', borderRadius: '4px', fontSize: '0.875rem' }}>
                  {passwordError}
                </div>
              )}

              {passwordSuccess && (
                <div style={{ padding: '0.5rem', marginBottom: '1rem', backgroundColor: '#e8f5e9', color: '#2e7d32', borderRadius: '4px', fontSize: '0.875rem' }}>
                  {passwordSuccess}
                </div>
              )}

              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>현재 비밀번호</label>
                <input
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                />
              </div>

              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>새 비밀번호</label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                />
              </div>

              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>새 비밀번호 확인</label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                />
              </div>

              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  onClick={handleChangePassword}
                  disabled={changingPassword}
                  style={{
                    flex: 1,
                    padding: '0.5rem',
                    backgroundColor: changingPassword ? '#ccc' : '#4CAF50',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: changingPassword ? 'not-allowed' : 'pointer',
                  }}
                >
                  {changingPassword ? '변경 중...' : '변경'}
                </button>
                <button
                  onClick={() => setShowPasswordModal(false)}
                  style={{
                    flex: 1,
                    padding: '0.5rem',
                    backgroundColor: '#9e9e9e',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                  }}
                >
                  취소
                </button>
              </div>
            </div>
          </div>
        )}
      </body>
    </html>
  );
}
