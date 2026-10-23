'use client';

import { useState } from 'react';

export function duplicateSubmitQuestion(tracking?: string) {
  return `오늘 같은 수취인, 같은 내용으로 이미 접수된 건이 있습니다.\n등기번호 ${tracking || '-'}\n\n중복인데 접수할까요?`;
}

export function useYesNo() {
  const [pending, setPending] = useState<{
    message: string;
    resolve: (value: boolean) => void;
  } | null>(null);

  function ask(message: string) {
    return new Promise<boolean>((resolve) => {
      setPending({ message, resolve });
    });
  }

  function answer(value: boolean) {
    pending?.resolve(value);
    setPending(null);
  }

  const dialog = pending ? (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 80,
        background: 'rgba(0,0,0,0.4)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1rem',
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="yes-no-title"
        style={{
          width: '100%',
          maxWidth: 420,
          background: 'var(--bg-card)',
          borderRadius: 16,
          boxShadow: 'var(--shadow-lg)',
          padding: '1.1rem',
        }}
      >
        <p id="yes-no-title" style={{ fontWeight: 700, marginBottom: '0.75rem', whiteSpace: 'pre-wrap' }}>
          {pending.message}
        </p>
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" className="btn btn-secondary" style={{ flex: 1 }} onClick={() => answer(false)}>
            아니오
          </button>
          <button type="button" className="btn btn-primary" style={{ flex: 1 }} onClick={() => answer(true)}>
            네
          </button>
        </div>
      </div>
    </div>
  ) : null;

  return { ask, dialog };
}
