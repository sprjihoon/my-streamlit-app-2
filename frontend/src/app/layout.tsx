'use client';

import './globals.css';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

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

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

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
            </nav>
          </aside>

          {/* 메인 콘텐츠 */}
          <main className="main-content">{children}</main>
        </div>
      </body>
    </html>
  );
}

