'use client';

import { KeyRound, LogOut, User } from 'lucide-react';
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
      <div className="sidebar-user">
        <div className="sidebar-user-actions">
          <button type="button" onClick={onLogout}>
            <LogOut size={12} strokeWidth={2} /> 로그아웃
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="sidebar-user">
      <div className="sidebar-user-main">
        <div className="sidebar-avatar" aria-hidden>
          <User size={14} strokeWidth={2} />
        </div>
        <div>
          <div className="sidebar-user-name">{user.nickname}</div>
          <div className="sidebar-role">{user.is_admin ? '관리자' : '사용자'}</div>
        </div>
      </div>
      <div className="sidebar-user-actions">
        <button type="button" onClick={onChangePassword}>
          <KeyRound size={12} strokeWidth={2} /> 비밀번호
        </button>
        <button type="button" onClick={onLogout}>
          <LogOut size={12} strokeWidth={2} /> 로그아웃
        </button>
      </div>
    </div>
  );
}
