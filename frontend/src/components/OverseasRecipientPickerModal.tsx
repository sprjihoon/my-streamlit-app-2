'use client';

import { useEffect, useMemo, useState } from 'react';
import { X } from 'lucide-react';
import type { OverseasSavedAddress } from '@/lib/api';

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '0.55rem 0.7rem',
  border: '1px solid var(--border)',
  borderRadius: '8px',
  fontFamily: 'inherit',
  fontSize: '0.9rem',
};

export default function OverseasRecipientPickerModal({
  items,
  selectedId,
  onSelect,
  onClose,
}: {
  items: OverseasSavedAddress[];
  selectedId: string;
  onSelect: (item: OverseasSavedAddress) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState('');

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase().replace(/\s+/g, '');
    if (!q) return items;
    return items.filter((a) => {
      const hay = `${a.label} ${a.recipient_name} ${a.countrycd} ${a.recipient_phone} ${a.addr1} ${a.addr2} ${a.addr3} ${a.zipcode}`
        .toLowerCase()
        .replace(/\s+/g, '');
      return hay.includes(q);
    });
  }, [items, query]);

  return (
    <div
      role="presentation"
      onClick={onClose}
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
        aria-labelledby="recipient-picker-title"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: 640,
          maxHeight: '88vh',
          background: 'var(--bg-card)',
          borderRadius: 16,
          boxShadow: 'var(--shadow-lg)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem 1.1rem 0.5rem' }}>
          <p id="recipient-picker-title" style={{ fontWeight: 700, margin: 0 }}>저장된 수취인</p>
          <button type="button" className="btn btn-secondary" onClick={onClose} style={{ padding: '0.25rem 0.45rem' }}>
            <X size={16} />
          </button>
        </div>
        <div style={{ padding: '0.5rem 1.1rem 0.75rem' }}>
          <input
            autoFocus
            style={inputStyle}
            value={query}
            placeholder="별칭, 이름, 국가, 전화, 주소 검색"
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 0.7rem 0.5rem' }}>
          {filtered.length === 0 ? (
            <p className="text-muted" style={{ padding: '1.25rem 0.5rem', textAlign: 'center' }}>
              {items.length === 0 ? '저장된 수취인이 없습니다.' : '검색 결과가 없습니다.'}
            </p>
          ) : (
            filtered.map((a) => {
              const active = String(a.id) === selectedId;
              const addr = [a.addr3, a.addr2, a.addr1, a.zipcode].filter(Boolean).join(', ');
              return (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => onSelect(a)}
                  style={{
                    display: 'block',
                    width: '100%',
                    textAlign: 'left',
                    padding: '0.75rem 0.85rem',
                    marginBottom: 6,
                    border: active ? '2px solid #0f172a' : '1px solid var(--border)',
                    borderRadius: 10,
                    background: active ? '#f8fafc' : '#fff',
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                  }}
                >
                  <div style={{ fontWeight: 700 }}>
                    {a.is_default ? '[기본] ' : ''}{a.label}
                    <span className="text-muted" style={{ fontWeight: 600, marginLeft: 8 }}>
                      {a.countrycd}
                    </span>
                  </div>
                  <div style={{ marginTop: 4, fontSize: '0.9rem' }}>{a.recipient_name}{a.recipient_phone ? ` · ${a.recipient_phone}` : ''}</div>
                  {addr ? (
                    <div className="text-muted" style={{ marginTop: 2, fontSize: '0.8rem' }}>{addr}</div>
                  ) : null}
                </button>
              );
            })
          )}
        </div>
        <div style={{ padding: '0.75rem 1.1rem 1rem', display: 'flex', gap: 8, borderTop: '1px solid var(--border)' }}>
          <button type="button" className="btn btn-secondary" style={{ flex: 1 }} onClick={onClose}>닫기</button>
          <a href="/overseas-recipients" className="btn btn-secondary" style={{ flex: 1, textAlign: 'center' }}>수취인 관리</a>
        </div>
      </div>
    </div>
  );
}
