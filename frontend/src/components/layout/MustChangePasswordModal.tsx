'use client';

import { useState } from 'react';
import { KeyRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function MustChangePasswordModal({ onSuccess }: { onSuccess: () => void }) {
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!newPw || newPw.length < 4) return setError('비밀번호는 4자 이상이어야 합니다.');
    if (newPw !== confirmPw) return setError('비밀번호가 일치하지 않습니다.');
    if (newPw === '123456') return setError('초기 비밀번호와 다른 비밀번호를 사용하세요.');
    setLoading(true);
    setError('');
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_URL}/auth/change-password?token=${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: '123456', new_password: newPw }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '변경 실패');
      localStorage.removeItem('must_change_password');
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : '변경 실패');
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open>
      <DialogContent
        overlayClassName="tw-z-[9999] tw-bg-black/70"
        className="tw-z-[10000] tw-w-[380px] tw-rounded-[12px] tw-p-8 tw-shadow-[0_20px_60px_rgba(0,0,0,0.3)]"
        onPointerDownOutside={(event) => event.preventDefault()}
        onInteractOutside={(event) => event.preventDefault()}
        onEscapeKeyDown={(event) => event.preventDefault()}
      >
        <div className="tw-mb-6 tw-text-center">
          <div className="tw-mb-3 tw-flex tw-justify-center">
            <div className="tw-flex tw-h-[52px] tw-w-[52px] tw-items-center tw-justify-center tw-rounded-full tw-bg-tillion-brand-light">
              <KeyRound size={24} className="tw-text-tillion-brand" />
            </div>
          </div>
          <DialogTitle asChild>
            <h3 className="tw-mb-2 tw-mt-0">비밀번호 변경 필요</h3>
          </DialogTitle>
          <DialogDescription className="tw-m-0 tw-text-[0.875rem] tw-text-[#6c757d]">
            초기 비밀번호(123456)를 변경해야 합니다.<br />
            새 비밀번호를 설정해주세요.
          </DialogDescription>
        </div>
        {error && (
          <div className="tw-mb-4 tw-rounded tw-bg-[#f8d7da] tw-p-2 tw-text-[0.875rem] tw-text-[#842029]">
            {error}
          </div>
        )}
        <form onSubmit={handleSubmit}>
          <Field label="새 비밀번호" labelClassName="tw-mb-1 tw-text-[0.875rem]">
            <Input
              type="password"
              value={newPw}
              onChange={e => setNewPw(e.target.value)}
              placeholder="새 비밀번호 (4자 이상)"
            />
          </Field>
          <Field label="새 비밀번호 확인" className="tw-mb-6" labelClassName="tw-mb-1 tw-text-[0.875rem]">
            <Input
              type="password"
              value={confirmPw}
              onChange={e => setConfirmPw(e.target.value)}
              placeholder="비밀번호 재입력"
            />
          </Field>
          <Button type="submit" variant="forcedSubmit" disabled={loading}>
            {loading ? '변경 중...' : '비밀번호 변경'}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
