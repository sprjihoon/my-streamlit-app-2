'use client';

import './globals.css';
import './operational.css';
import './data.css';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { MustChangePasswordModal } from '@/components/layout/MustChangePasswordModal';
import { PasswordChangeModal } from '@/components/layout/PasswordChangeModal';
import { Sidebar } from '@/components/layout/Sidebar';
import type { User } from '@/components/layout/types';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [mustChangePw, setMustChangePw] = useState(false);
  const [showPasswordModal, setShowPasswordModal] = useState(false);

  // 로그인 페이지는 레이아웃 적용 안함
  const isLoginPage = pathname === '/login';
  const isPublicPage = pathname === '/estimate';
  const isMobileWorkPage = pathname.startsWith('/inbound/') && pathname !== '/inbound-log';
  const isSharePage = pathname.startsWith('/share/');
  const isPrintPage = pathname.startsWith('/overseas-print/');

  useEffect(() => {
    if (isLoginPage || isPublicPage || isMobileWorkPage || isSharePage || isPrintPage) {
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
      // must_change_password 체크
      const mcp = localStorage.getItem('must_change_password');
      if (mcp === 'true') setMustChangePw(true);
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

  // 로그인 페이지 또는 공개 페이지 (사이드바 없이)
  if (isLoginPage || isPublicPage || isMobileWorkPage || isSharePage || isPrintPage) {
    return (
      <html lang="ko">
        <head>
          <title>{isPrintPage ? '해외배송 출력서류' : isPublicPage ? '견적서 만들기' : isMobileWorkPage ? '입고 작업' : isSharePage ? '입고 현황' : '로그인'} - 틸리언 그룹웨어</title>
          <link rel="icon" href="/favicon.png" type="image/png" />
          <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />
        </head>
        <body className={isPublicPage ? 'tw-min-h-screen tw-bg-black' : undefined}>{children}</body>
      </html>
    );
  }

  // 로딩 중
  if (loading) {
    return (
      <html lang="ko">
        <head>
          <title>틸리언 그룹웨어</title>
          <meta name="viewport" content="width=device-width, initial-scale=1" />
        </head>
        <body>
          <div className="tw-flex tw-h-screen tw-items-center tw-justify-center">
            <p>로딩 중...</p>
          </div>
        </body>
      </html>
    );
  }

  return (
    <html lang="ko">
      <head>
        <title>틸리언 그룹웨어</title>
        <link rel="icon" href="/favicon.png" type="image/png" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body>
        <div className="layout">
          <Sidebar
            user={user}
            pathname={pathname}
            onLogout={handleLogout}
            onChangePassword={() => setShowPasswordModal(true)}
          />
          <main className="main-content">
            {children}
          </main>
        </div>

        {mustChangePw && (
          <MustChangePasswordModal onSuccess={() => setMustChangePw(false)} />
        )}

        {showPasswordModal && (
          <PasswordChangeModal onClose={() => setShowPasswordModal(false)} />
        )}
      </body>
    </html>
  );
}
