'use client';

import Link from 'next/link';
import { CreditCard, Settings, ShieldCheck } from 'lucide-react';
import { NavGroup } from './NavGroup';
import { UserPanel } from './UserPanel';
import { ADMIN_NAV_ITEMS, BILLING_INVOICE_NAV_ITEMS, IC, INBOUND_NAV_GROUP, NAV_GROUPS, RETURN_INFO_LOG_NAV_ITEM, RETURN_INFO_NAV_ITEM, canSeeNavItem } from './navigation';
import type { User } from './types';

export function Sidebar({
  user,
  pathname,
  onChangePassword,
  onLogout,
}: {
  user: User | null;
  pathname: string;
  onChangePassword: () => void;
  onLogout: () => void;
}) {
  const inboundItems = INBOUND_NAV_GROUP.items.filter((item) => canSeeNavItem(user, item));

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-mark" aria-hidden>
          <ShieldCheck size={16} strokeWidth={2.25} />
        </div>
        <div>
          <div className="sidebar-brand-name">틸리언</div>
          <div className="sidebar-brand-sub">그룹웨어</div>
        </div>
      </div>

      <UserPanel user={user} onChangePassword={onChangePassword} onLogout={onLogout} />

      <nav>
        {(user?.is_admin
          ? NAV_GROUPS
          : [...NAV_GROUPS].sort((a, b) =>
              a.key === 'groupware' ? -1 : b.key === 'groupware' ? 1 : 0
            )
        ).map(group => {
          const visibleItems = group.items.filter((item) => canSeeNavItem(user, item));
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

        {inboundItems.length > 0 && (
          <NavGroup
            label={INBOUND_NAV_GROUP.label}
            icon={INBOUND_NAV_GROUP.icon}
            items={inboundItems}
            pathname={pathname}
          />
        )}

        <Link
          href={RETURN_INFO_NAV_ITEM.href}
          className={pathname === RETURN_INFO_NAV_ITEM.href ? 'active' : ''}
          style={{ marginTop: '0.35rem' }}
        >
          <span className="tw-flex tw-shrink-0 tw-items-center">{RETURN_INFO_NAV_ITEM.icon}</span>
          <span>{RETURN_INFO_NAV_ITEM.label}</span>
        </Link>
        <Link
          href={RETURN_INFO_LOG_NAV_ITEM.href}
          className={pathname === RETURN_INFO_LOG_NAV_ITEM.href ? 'active' : ''}
        >
          <span className="tw-flex tw-shrink-0 tw-items-center">{RETURN_INFO_LOG_NAV_ITEM.icon}</span>
          <span>{RETURN_INFO_LOG_NAV_ITEM.label}</span>
        </Link>

        {user?.is_admin && (
          <NavGroup
            label="실 청구서"
            icon={<CreditCard {...IC} />}
            items={BILLING_INVOICE_NAV_ITEMS}
            pathname={pathname}
          />
        )}

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
  );
}
