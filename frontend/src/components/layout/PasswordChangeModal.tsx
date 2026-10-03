'use client';

import { useState } from 'react';
import { KeyRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function PasswordChangeModal({ onClose }: { onClose: () => void }) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null);
  const [changingPassword, setChangingPassword] = useState(false);

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
        onClose();
      }, 1500);
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : '비밀번호 변경 실패');
    } finally {
      setChangingPassword(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent
        aria-describedby={undefined}
        className="tw-w-[350px] tw-rounded-[8px] tw-p-8"
        onEscapeKeyDown={(event) => event.preventDefault()}
      >
        <DialogTitle asChild>
          <h3 className="tw-mb-4 tw-flex tw-items-center tw-gap-2">
            <KeyRound size={18} className="tw-text-tillion-brand" /> 비밀번호 변경
          </h3>
        </DialogTitle>

        {passwordError && (
          <div className="tw-mb-4 tw-rounded tw-bg-[#ffebee] tw-p-2 tw-text-[0.875rem] tw-text-[#c62828]">
            {passwordError}
          </div>
        )}

        {passwordSuccess && (
          <div className="tw-mb-4 tw-rounded tw-bg-[#e8f5e9] tw-p-2 tw-text-[0.875rem] tw-text-[#2e7d32]">
            {passwordSuccess}
          </div>
        )}

        <Field label="현재 비밀번호">
          <Input
            tone="plain"
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            className="tw-border-[#ddd] tw-p-2"
          />
        </Field>

        <Field label="새 비밀번호">
          <Input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="tw-border-[#ddd] tw-p-2"
          />
        </Field>

        <Field label="새 비밀번호 확인">
          <Input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="tw-border-[#ddd] tw-p-2"
          />
        </Field>

        <div className="tw-flex tw-gap-2">
          <Button variant="changeSubmit" onClick={handleChangePassword} disabled={changingPassword}>
            {changingPassword ? '변경 중...' : '변경'}
          </Button>
          <Button variant="cancel" onClick={onClose}>
            취소
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
