'use client';

import { useState } from 'react';
import { KeyRound } from 'lucide-react';
import Alert from '@/components/Alert';
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
        overlayClassName="tw-z-[9999] tw-bg-[rgba(16,18,32,0.62)]"
        className="ui-dialog tw-z-[10000]"
        onPointerDownOutside={(event) => event.preventDefault()}
        onInteractOutside={(event) => event.preventDefault()}
        onEscapeKeyDown={(event) => event.preventDefault()}
      >
        <div className="ui-dialog-header">
          <DialogTitle asChild>
            <h3>
              <KeyRound size={16} className="tw-text-tillion-brand" /> 비밀번호 변경 필요
            </h3>
          </DialogTitle>
          <DialogDescription>
            초기 비밀번호(123456)를 변경해야 합니다. 새 비밀번호를 설정해주세요.
          </DialogDescription>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="ui-dialog-body">
            {error && <Alert type="error">{error}</Alert>}
            <Field label="새 비밀번호" required hint="4자 이상, 초기 비밀번호와 달라야 합니다.">
              <Input type="password" value={newPw} onChange={e => setNewPw(e.target.value)} placeholder="새 비밀번호" />
            </Field>
            <Field label="새 비밀번호 확인" required>
              <Input type="password" value={confirmPw} onChange={e => setConfirmPw(e.target.value)} placeholder="비밀번호 재입력" />
            </Field>
          </div>
          <div className="ui-dialog-actions is-stack">
            <Button type="submit" variant="primary" disabled={loading} className="tw-w-full">
              {loading ? '변경 중...' : '비밀번호 변경'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
