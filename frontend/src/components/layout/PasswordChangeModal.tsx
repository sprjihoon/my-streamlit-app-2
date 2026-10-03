'use client';

import { useState } from 'react';
import { KeyRound } from 'lucide-react';
import Alert from '@/components/Alert';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
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
        className="ui-dialog"
        overlayClassName="tw-bg-[rgba(16,18,32,0.48)]"
        onEscapeKeyDown={(event) => event.preventDefault()}
      >
        <div className="ui-dialog-header">
          <DialogTitle asChild>
            <h3>
              <KeyRound size={16} className="tw-text-tillion-brand" /> 비밀번호 변경
            </h3>
          </DialogTitle>
          <DialogDescription>현재 비밀번호를 확인한 뒤 새 비밀번호를 저장합니다.</DialogDescription>
        </div>

        <div className="ui-dialog-body">
          {passwordError && <Alert type="error">{passwordError}</Alert>}
          {passwordSuccess && <Alert type="success">{passwordSuccess}</Alert>}

          <Field label="현재 비밀번호" required>
            <Input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
          </Field>
          <Field label="새 비밀번호" required hint="4자 이상">
            <Input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
          </Field>
          <Field label="새 비밀번호 확인" required>
            <Input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
          </Field>
        </div>

        <div className="ui-dialog-actions">
          <Button variant="secondary" onClick={onClose}>취소</Button>
          <Button variant="primary" onClick={handleChangePassword} disabled={changingPassword}>
            {changingPassword ? '변경 중...' : '변경'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
