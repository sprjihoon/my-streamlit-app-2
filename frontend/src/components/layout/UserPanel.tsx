'use client';

import { KeyRound, LogOut, User } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { User as AppUser } from './types';

export function UserPanel({
  user,
  onChangePassword,
  onLogout,
}: {
  user: AppUser | null;
  onChangePassword: () => void;
  onLogout: () => void;
}) {
  if (!user) {
    return (
      <div className="tw-mx-[0.6rem] tw-my-3">
        <Button variant="sidebarLogout" onClick={onLogout}>
          <LogOut size={13} strokeWidth={2} className="tw-mr-[0.3rem]" /> 로그아웃
        </Button>
      </div>
    );
  }

  return (
    <div className="tw-mx-[0.6rem] tw-my-3 tw-rounded-[8px] tw-border tw-border-solid tw-border-white/10 tw-bg-white/[0.07] tw-p-3">
      <div className="tw-mb-2 tw-flex tw-items-center tw-gap-2">
        <div className="tw-flex tw-h-[32px] tw-w-[32px] tw-shrink-0 tw-items-center tw-justify-center tw-rounded-full tw-bg-[linear-gradient(135deg,#4361ee,#7b9cff)] tw-text-[0.8rem] tw-font-bold tw-text-white">
          <User size={15} strokeWidth={2} />
        </div>
        <div>
          <div className="tw-text-[0.875rem] tw-font-bold tw-leading-[1.2] tw-text-white">
            {user.nickname}
          </div>
          <Badge variant="role">{user.is_admin ? '관리자' : '일반 사용자'}</Badge>
        </div>
      </div>
      <div className="tw-flex tw-gap-[0.375rem]">
        <Button variant="sidebarPrimary" onClick={onChangePassword}>
          <KeyRound size={11} strokeWidth={2} /> 비번변경
        </Button>
        <Button variant="sidebarMuted" onClick={onLogout}>
          <LogOut size={11} strokeWidth={2} /> 로그아웃
        </Button>
      </div>
    </div>
  );
}
