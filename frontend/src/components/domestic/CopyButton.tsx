'use client';

import { useState, type MouseEvent } from 'react';

export function CopyButton({ value }: { value: string }) {
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  if (!value) return <span>-</span>;

  async function copy(event: MouseEvent<HTMLButtonElement>) {
    event.preventDefault();
    event.stopPropagation();
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error('clipboard unavailable');
      }
      await navigator.clipboard.writeText(value);
      setNote({ ok: true, text: '복사했습니다.' });
    } catch {
      setNote({ ok: false, text: '복사하지 못했습니다. 송장번호를 직접 선택해 복사해주세요.' });
    }
  }

  return (
    <span className="domestic-copy">
      <span className="domestic-mono">{value}</span>
      <button type="button" className="btn btn-ghost domestic-copy-btn" onClick={(event) => void copy(event)}>
        복사
      </button>
      {note ? (
        <span role="status" className={note.ok ? 'domestic-copy-ok' : 'domestic-copy-bad'}>
          {note.text}
        </span>
      ) : null}
    </span>
  );
}
