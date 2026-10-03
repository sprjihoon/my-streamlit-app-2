'use client';

import { CreditCard, Settings, ShieldCheck } from 'lucide-react';
import { NavGroup } from './NavGroup';
import { UserPanel } from './UserPanel';
import { ADMIN_NAV_ITEMS, BILLING_INVOICE_NAV_ITEMS, IC, NAV_GROUPS, canSeeNavItem } from './navigation';
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
  return (
    <aside className="sidebar">
      <h1>
        <ShieldCheck size={18} strokeWidth={2} className="tw-shrink-0 tw-text-[#7b9cff]" />
        틸리언 그룹웨어
      </h1>

      <UserPanel user={user} onChangePassword={onChangePassword} onLogout={onLogout} />

      <nav className="!tw-gap-[2px]">
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
