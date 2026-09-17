'use client';

import { Info, X } from 'lucide-react';

export interface SuggestedAddress {
  addr3: string;
  addr2: string;
  addr1: string;
  zip: string;
  formattedAddress?: string;
}

interface Props {
  original: SuggestedAddress;
  suggested: SuggestedAddress;
  onKeepOriginal: () => void;
  onUseSuggested: () => void;
}

function formatSingle(a: SuggestedAddress): string {
  return [a.addr3, a.addr2, a.addr1, a.zip].filter(Boolean).join(', ');
}

export default function AddressSuggestionDialog({
  original,
  suggested,
  onKeepOriginal,
  onUseSuggested,
}: Props) {
  const suggestedDisplay = suggested.formattedAddress || formatSingle(suggested);
  const originalDisplay = formatSingle(original);

  return (
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
        style={{
          width: '100%',
          maxWidth: 420,
          background: 'var(--bg-card)',
          borderRadius: 16,
          boxShadow: 'var(--shadow-lg)',
          overflow: 'hidden',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem 1.1rem 0.5rem' }}>
          <p style={{ fontWeight: 700 }}>구글 추천 주소로 변경하시겠어요?</p>
          <button type="button" className="btn btn-secondary" onClick={onKeepOriginal} style={{ padding: '0.25rem 0.45rem' }}>
            <X size={16} />
          </button>
        </div>
        <div style={{ padding: '0.75rem 1.1rem 1.1rem', display: 'flex', flexDirection: 'column', gap: '0.7rem' }}>
          <div style={{ background: 'var(--bg-muted)', border: '1px solid var(--border)', borderRadius: 10, padding: '0.75rem' }}>
            <p className="text-muted" style={{ fontSize: '0.7rem', marginBottom: 4 }}>입력한 주소</p>
            <p>{originalDisplay}</p>
          </div>
          <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>↓</div>
          <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 10, padding: '0.75rem' }}>
            <p style={{ fontSize: '0.7rem', color: '#2563eb', marginBottom: 4, fontWeight: 700 }}>Google 추천 주소</p>
            <p>{suggestedDisplay}</p>
          </div>
          <p className="text-muted" style={{ fontSize: '0.8rem', display: 'flex', gap: 6 }}>
            <Info size={14} />
            추천 주소를 사용해도 접수 전까지 수정할 수 있습니다.
          </p>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="btn btn-secondary" style={{ flex: 1 }} onClick={onKeepOriginal}>
              내 주소 유지
            </button>
            <button type="button" className="btn btn-primary" style={{ flex: 1 }} onClick={onUseSuggested}>
              추천 주소 사용
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
