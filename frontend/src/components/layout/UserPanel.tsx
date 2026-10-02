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
      <div style={{ margin: '0.75rem 0.6rem' }}>
        <button
          onClick={onLogout}
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
    );
  }

  return (
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
          onClick={onChangePassword}
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
          onClick={onLogout}
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
  );
}
