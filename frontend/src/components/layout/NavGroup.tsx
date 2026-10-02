'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import type { NavItem } from './types';

export function NavGroup({
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
        {items.map(item => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
          <Link
            key={item.href}
            href={item.href}
            className={active ? 'active' : ''}
            style={{ paddingLeft: '1rem', fontSize: '0.8375rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}
          >
            <span style={{ display: 'flex', alignItems: 'center', opacity: active ? 1 : 0.65, flexShrink: 0 }}>{item.icon}</span>
            <span>{item.label}</span>
          </Link>
          );
        })}
      </div>
    </div>
  );
}
