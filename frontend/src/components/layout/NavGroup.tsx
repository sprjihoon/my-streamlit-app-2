'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
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
    <div className="tw-mb-[2px]">
      <button
        onClick={() => setOpen(o => !o)}
        className={cn(
          'tw-mt-2 tw-flex tw-w-full tw-cursor-pointer tw-items-center tw-justify-between tw-rounded-[6px] tw-border-0 tw-px-3 tw-py-[0.45rem] tw-font-[inherit] tw-text-[0.675rem] tw-font-bold tw-uppercase tw-tracking-[0.08em] tw-transition-all tw-duration-150',
          hasActive ? 'tw-bg-white/[0.12] tw-text-white' : 'tw-bg-transparent tw-text-white/50',
        )}
      >
        <span className="tw-flex tw-items-center tw-gap-2">
          <span className="tw-flex tw-items-center tw-opacity-80">{icon}</span>
          <span>{label}</span>
        </span>
        <span
          className={cn(
            'tw-text-[0.55rem] tw-opacity-70 tw-transition-transform tw-duration-200',
            open ? 'tw-rotate-180' : 'tw-rotate-0',
          )}
        >
          ▼
        </span>
      </button>

      <div
        className="tw-overflow-hidden tw-transition-[max-height] tw-duration-[250ms] tw-ease-in-out"
        style={{ maxHeight: open ? `${items.length * 40}px` : '0px' }}
      >
        {items.map(item => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(active ? 'active' : '', '!tw-gap-2 !tw-pl-4 !tw-text-[0.8375rem]')}
            >
              <span className={cn('tw-flex tw-shrink-0 tw-items-center', active ? 'tw-opacity-100' : 'tw-opacity-65')}>
                {item.icon}
              </span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
