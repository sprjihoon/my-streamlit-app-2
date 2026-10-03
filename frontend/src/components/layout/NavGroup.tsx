'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
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

  useEffect(() => {
    if (hasActive) setOpen(true);
  }, [hasActive]);

  return (
    <div className="sidebar-group">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className={cn('sidebar-group-btn', hasActive && 'is-active')}
      >
        <span className="sidebar-group-label">
          {icon}
          <span>{label}</span>
        </span>
        <ChevronDown size={13} className={cn('sidebar-chevron', open && 'is-open')} />
      </button>

      <div className="sidebar-items" style={{ maxHeight: open ? `${items.length * 36}px` : '0px' }}>
        {items.map(item => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link key={item.href} href={item.href} className={active ? 'active' : ''}>
              <span className="tw-flex tw-shrink-0 tw-items-center">{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
