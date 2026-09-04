'use client';

import './globals.css';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import React, { useEffect, useState } from 'react';
import {
  LayoutDashboard, ClipboardList, Scissors, Upload, Link2, List, DollarSign,
  BarChart2, FileText, FileSpreadsheet, TrendingUp, CalendarDays,
  Calendar, Receipt, BadgeCheck, Globe, CreditCard, Package,
  PlusCircle, Users, ScrollText, Settings, ChevronDown,
  User, LogOut, KeyRound, ShieldCheck,
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ─────────────────────────────────────
// 아코디언 네비게이션 그룹 컴포넌트
// ─────────────────────────────────────
interface NavItem { href: string; label: string; icon: React.ReactNode; adminOnly?: boolean; }

function NavGroup({
  label,
  icon,
  items,
  pathname,
  defaultOpen,
}: {
  label: string;
  icon: React.ReactNode;
  items: NavItem[];
  pathname: string;
  defaultOpen?: boolean;
}) {
  const hasActive = items.some(i => i.href === pathname);
  const [open, setOpen] = useState(defaultOpen || hasActive);

  // 경로 바뀌면 active 그룹 자동 열기
  useEffect(() => {
    if (hasActive) setOpen(true);
  }, [hasActive]);

  return (
    <div style={{ marginBottom: '2px' }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0.45rem 0.75rem',
          background: hasActive ? 'rgba(255,255,255,0.12)' : 'transparent',
          border: 'none',
          borderRadius: '6px',
          color: hasActive ? '#ffffff' : 'rgba(255,255,255,0.5)',
          cursor: 'pointer',
          fontSize: '0.675rem',
          fontWeight: 700,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          transition: 'all 0.15s',
          marginTop: '0.5rem',
          fontFamily: 'inherit',
        }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ display: 'flex', alignItems: 'center', opacity: 0.8 }}>{icon}</span>
          <span>{label}</span>
        </span>
        <span style={{
          fontSize: '0.55rem',
          opacity: 0.7,
          transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
          transition: 'transform 0.2s',
        }}>▼</span>
      </button>

      <div style={{
        overflow: 'hidden',
        maxHeight: open ? `${items.length * 40}px` : '0px',
        transition: 'max-height 0.25s ease',
      }}>
        {items.map(item => (
          <Link
            key={item.href}
            href={item.href}
            className={pathname === item.href ? 'active' : ''}
            style={{ paddingLeft: '1rem', fontSize: '0.8375rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}
          >
            <span style={{ display: 'flex', alignItems: 'center', opacity: pathname === item.href ? 1 : 0.65, flexShrink: 0 }}>{item.icon}</span>
            <span>{item.label}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

interface User {
  user_id: number;
  username: string;
  nickname: string;
  is_admin: boolean;
  position?: string;
  department?: string;
}

// 최초 로그인 비밀번호 변경 강제 모달
function MustChangePasswordModal({ onSuccess }: { onSuccess: () => void }) {
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

const IC = { size: 14, strokeWidth: 1.75 };

// adminOnly: true → 관리자(is_admin)만 표시
// adminOnly 없음 → 모든 로그인 사용자 표시
const NAV_GROUPS = [
  {
    key: 'home',
    label: '기본',
    icon: <LayoutDashboard {...IC} />,
    items: [
      { href: '/', label: '대시보드', icon: <LayoutDashboard {...IC} />, adminOnly: true },
      { href: '/work-log', label: '작업일지', icon: <ClipboardList {...IC} />, adminOnly: true },
      { href: '/repair-log', label: '수선작업일지', icon: <Scissors {...IC} />, adminOnly: true },
      { href: '/upload', label: '데이터 업로드', icon: <Upload {...IC} />, adminOnly: true },
      { href: '/mapping', label: '업체 매핑 관리', icon: <Link2 {...IC} />, adminOnly: true },
      { href: '/vendors', label: '매핑 리스트', icon: <List {...IC} />, adminOnly: true },
      { href: '/rates', label: '요금표 관리', icon: <DollarSign {...IC} />, adminOnly: true },
      { href: '/insights', label: '데이터 인사이트', icon: <TrendingUp {...IC} /> },
    ],
  },
  {
    key: 'invoice',
    label: '인보이스',
    icon: <BarChart2 {...IC} />,
    items: [
      { href: '/invoice', label: '인보이스 계산', icon: <FileSpreadsheet {...IC} />, adminOnly: true },
      { href: '/invoice-list', label: '인보이스 목록', icon: <List {...IC} />, adminOnly: true },
      { href: '/invoice-analytics', label: '청구금액 분석', icon: <TrendingUp {...IC} /> },
    ],
  },
  {
    key: 'estimate',
    label: '견적서',
    icon: <FileText {...IC} />,
    items: [
      { href: '/estimate', label: '견적서 만들기', icon: <FileText {...IC} /> },
      { href: '/estimate-list', label: '견적서 목록', icon: <List {...IC} /> },
      { href: '/estimate-analytics', label: '견적서 분석', icon: <BarChart2 {...IC} /> },
    ],
  },
  {
    key: 'groupware',
    label: '그룹웨어',
    icon: <CalendarDays {...IC} />,
    items: [
      { href: '/leave', label: '연월차 관리', icon: <CalendarDays {...IC} /> },
      { href: '/leave/calendar', label: '연차 달력', icon: <Calendar {...IC} /> },
      { href: '/receipts', label: '영수증 처리', icon: <Receipt {...IC} /> },
      { href: '/certificates', label: '증명서 발급', icon: <BadgeCheck {...IC} /> },
    ],
  },
  {
    key: 'marketing',
    label: '마케팅',
    icon: <Globe {...IC} />,
    items: [
      { href: '/wp-analytics', label: '사이트 방문 분석', icon: <Globe {...IC} /> },
    ],
  },
];

const BILLING_INVOICE_NAV_ITEMS = [
  { href: '/billing-invoice', label: '실 인보이스 관리', icon: <CreditCard {...IC} /> },
  { href: '/billing-invoice/analytics', label: '청구금액 분석', icon: <BarChart2 {...IC} /> },
];

const ADMIN_NAV_ITEMS = [
  { href: '/storage', label: '보관료 관리', icon: <Package {...IC} /> },
  { href: '/vendor-charges', label: '추가비용 관리', icon: <PlusCircle {...IC} /> },
  { href: '/users', label: '사용자 관리', icon: <Users {...IC} /> },
  { href: '/logs', label: '활동 로그', icon: <ScrollText {...IC} /> },
  { href: '/settings', label: '회사 설정', icon: <Settings {...IC} /> },
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
  const [mustChangePw, setMustChangePw] = useState(false);

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
  const isPublicPage = pathname === '/estimate';

  useEffect(() => {
    if (isLoginPage || isPublicPage) {
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

  // 로그인 페이지 또는 공개 페이지 (사이드바 없이)
  if (isLoginPage || isPublicPage) {
    return (
      <html lang="ko">
        <head>
          <title>{isPublicPage ? '견적서 만들기' : '로그인'} - 틸리언 그룹웨어</title>
          <link rel="icon" href="/favicon.png" type="image/png" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
        </head>
        <body style={isPublicPage ? { background: '#000', minHeight: '100vh' } : undefined}>{children}</body>
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
        <title>틸리언 그룹웨어</title>
        <link rel="icon" href="/favicon.png" type="image/png" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body>
        <div className="layout">
          {/* 사이드바 */}
          <aside className="sidebar">
            <h1>
              <ShieldCheck size={18} strokeWidth={2} style={{ color: '#7b9cff', flexShrink: 0 }} />
              틸리언 그룹웨어
            </h1>

            {/* 사용자 정보 */}
            {user ? (
              <div style={{
                margin: '0.75rem 0.6rem',
                padding: '0.75rem',
                background: 'rgba(255,255,255,0.07)',
                borderRadius: '8px',
                border: '1px solid rgba(255,255,255,0.1)',
              }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  marginBottom: '0.5rem',
                }}>
                  <div style={{
                    width: '32px',
                    height: '32px',
                    borderRadius: '50%',
                    background: 'linear-gradient(135deg, #4361ee, #7b9cff)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '0.8rem',
                    fontWeight: 700,
                    color: '#fff',
                    flexShrink: 0,
                  }}>
                    <User size={15} strokeWidth={2} />
                  </div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '0.875rem', color: '#fff', lineHeight: 1.2 }}>
                      {user.nickname}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.45)', marginTop: '1px' }}>
                      {user.is_admin ? '관리자' : '일반 사용자'}
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '0.375rem' }}>
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
                      padding: '0.3rem 0.4rem',
                      fontSize: '0.72rem',
                      fontWeight: 600,
                      background: 'rgba(67,97,238,0.7)',
                      color: '#fff',
                      border: 'none',
                      borderRadius: '5px',
                      cursor: 'pointer',
                      fontFamily: 'inherit',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '0.3rem',
                    }}
                  >
                    <KeyRound size={11} strokeWidth={2} /> 비번변경
                  </button>
                  <button
                    onClick={handleLogout}
                    style={{
                      flex: 1,
                      padding: '0.3rem 0.4rem',
                      fontSize: '0.72rem',
                      fontWeight: 600,
                      background: 'rgba(255,255,255,0.1)',
                      color: 'rgba(255,255,255,0.75)',
                      border: '1px solid rgba(255,255,255,0.15)',
                      borderRadius: '5px',
                      cursor: 'pointer',
                      fontFamily: 'inherit',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '0.3rem',
                    }}
                  >
                    <LogOut size={11} strokeWidth={2} /> 로그아웃
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ margin: '0.75rem 0.6rem' }}>
                <button
                  onClick={handleLogout}
                  style={{
                    width: '100%',
                    padding: '0.4rem',
                    fontSize: '0.8rem',
                    background: 'rgba(255,255,255,0.1)',
                    color: 'rgba(255,255,255,0.75)',
                    border: '1px solid rgba(255,255,255,0.15)',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                  }}
                >
                  <LogOut size={13} strokeWidth={2} style={{ marginRight: '0.3rem' }} /> 로그아웃
                </button>
              </div>
            )}
            
            <nav style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
              {/* 일반 그룹 (아코디언) — adminOnly 항목은 관리자만 표시 */}
              {/* 비관리자는 그룹웨어 카테고리를 맨 위로 */}
              {(user?.is_admin
                ? NAV_GROUPS
                : [...NAV_GROUPS].sort((a, b) =>
                    a.key === 'groupware' ? -1 : b.key === 'groupware' ? 1 : 0
                  )
              ).map(group => {
                const visibleItems = group.items.filter(
                  item => user?.is_admin || !item.adminOnly
                );
                if (visibleItems.length === 0) return null;
                return (
                  <NavGroup
                    key={group.key}
                    label={group.label}
                    icon={group.icon}
                    items={visibleItems}
                    pathname={pathname}
                  />
                );
              })}

              {/* 실 인보이스 (관리자 전용) */}
              {user?.is_admin && (
                <NavGroup
                  label="실 청구서"
                  icon={<CreditCard {...IC} />}
                  items={BILLING_INVOICE_NAV_ITEMS}
                  pathname={pathname}
                />
              )}

              {/* 관리자 전용 */}
              {user?.is_admin && (
                <NavGroup
                  label="관리자"
                  icon={<Settings {...IC} />}
                  items={ADMIN_NAV_ITEMS}
                  pathname={pathname}
                />
              )}
            </nav>
          </aside>

          {/* 메인 콘텐츠 */}
          <main className="main-content">
            {children}
          </main>
        </div>

        {/* 최초 로그인 비밀번호 강제 변경 모달 */}
        {mustChangePw && (
          <MustChangePasswordModal onSuccess={() => setMustChangePw(false)} />
        )}

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
              <h3 style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <KeyRound size={18} style={{ color: '#4361ee' }} /> 비밀번호 변경
              </h3>

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
