'use client';

import { useEffect, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';

const PRINT_STYLE = `
.a4-preview-sheet {
  width: min(210mm, 100%);
  aspect-ratio: 210 / 297;
  margin: 0 auto 16px;
  background: #fff;
  box-shadow: 0 8px 24px rgba(0,0,0,.18);
  overflow: hidden;
}
.a4-preview-sheet img { width: 100%; height: 100%; object-fit: fill; display: block; }
@media print {
  body * { visibility: hidden !important; }
  #a4-print-area, #a4-print-area * { visibility: visible !important; }
  #a4-print-area { position: absolute; left: 0; top: 0; width: 210mm; background: #fff; }
  .a4-preview-bar { display: none !important; }
  .a4-preview-hidden { display: block !important; }
  .a4-preview-sheet {
    width: 210mm; height: 297mm; margin: 0; box-shadow: none;
    page-break-after: always; break-after: page;
  }
  @page { size: A4 portrait; margin: 0; }
}
`;

function Pages({ pages, title }: { pages: string[]; title: string }) {
  return (
    <>
      {pages.map((page, index) => (
        <div className="a4-preview-sheet" key={index}>
          <img
            src={page.startsWith('data:') ? page : `data:image/png;base64,${page}`}
            alt={`${title} ${index + 1}쪽`}
          />
        </div>
      ))}
    </>
  );
}

export function A4Preview({
  pages,
  onClose,
  overlay = false,
  title = '근로계약서',
  onConfirm,
  confirmLabel = '이 내용으로 날인',
  confirmDisabled = false,
}: {
  pages: string[];
  onClose?: () => void;
  overlay?: boolean;
  title?: string;
  onConfirm?: () => void;
  confirmLabel?: string;
  confirmDisabled?: boolean;
}) {
  const [pageIndex, setPageIndex] = useState(0);
  const [seenLast, setSeenLast] = useState(pages.length <= 1);

  useEffect(() => {
    setPageIndex(0);
    setSeenLast(pages.length <= 1);
  }, [pages]);

  useEffect(() => {
    if (pageIndex >= pages.length - 1) setSeenLast(true);
  }, [pageIndex, pages.length]);
  useEffect(() => {
    const style = document.createElement('style');
    style.setAttribute('data-a4-preview', '1');
    style.textContent = PRINT_STYLE;
    document.head.appendChild(style);
    return () => style.remove();
  }, []);

  useEffect(() => {
    if (!overlay || !onClose) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose?.();
      if (event.key === 'ArrowLeft') setPageIndex((current) => Math.max(0, current - 1));
      if (event.key === 'ArrowRight') setPageIndex((current) => Math.min(pages.length - 1, current + 1));
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [overlay, onClose, pages.length]);

  if (overlay) {
    const modal = (
      <div
        className="a4-preview-backdrop"
        role="dialog"
        aria-modal="true"
        aria-label="출력 미리보기"
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 2000,
          background: 'rgba(15, 23, 42, 0.55)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '3vh 16px',
        }}
        onMouseDown={(event) => {
          if (event.target === event.currentTarget) onClose?.();
        }}
      >
        <div
          className="a4-preview-modal"
          style={{
            width: 'min(920px, 100%)',
            maxHeight: '94vh',
            background: '#fff',
            borderRadius: 14,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            boxShadow: '0 24px 60px rgba(15, 23, 42, 0.35)',
          }}
          onMouseDown={(event) => event.stopPropagation()}
        >
          <div
            className="a4-preview-bar"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '12px 16px',
              borderBottom: '1px solid #e5e7eb',
            }}
          >
            <strong style={{ fontSize: 15 }}>{onConfirm ? '계약서 확인' : '출력 미리보기'}</strong>
            <span style={{ color: '#6b7280', fontSize: 13 }}>{pageIndex + 1} / {pages.length}장</span>
            <button type="button" onClick={() => setPageIndex((current) => Math.max(0, current - 1))} disabled={pageIndex === 0} style={barButton}>이전</button>
            <button type="button" onClick={() => setPageIndex((current) => Math.min(pages.length - 1, current + 1))} disabled={pageIndex >= pages.length - 1} style={{ ...barButton, marginRight: 'auto' }}>다음</button>
            {onConfirm && (
              <button type="button" onClick={onConfirm} disabled={!seenLast || confirmDisabled} style={{ ...barButton, background: seenLast ? '#166534' : '#9ca3af' }}>
                {seenLast ? confirmLabel : '마지막 장까지 보세요'}
              </button>
            )}
            <button type="button" onClick={() => window.print()} style={barButton}>인쇄</button>
            <button type="button" onClick={onClose} style={barButton}>닫기</button>
          </div>
          <div className="a4-preview-body" id="a4-print-area" style={{ overflow: 'auto', background: '#e5e7eb', padding: '16px 12px' }}>
            {pages.map((page, index) => (
              <div key={index} className={index === pageIndex ? undefined : 'a4-preview-hidden'} style={index === pageIndex ? undefined : { display: 'none' }}>
                <Pages pages={[page]} title={`${title} ${index + 1}`} />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
    if (typeof document === 'undefined') return modal;
    return createPortal(modal, document.body);
  }

  return (
    <div style={{ background: '#d1d5db', minHeight: '100vh' }}>
      <div className="a4-preview-bar" style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 16px', background: '#111827', color: '#e5e7eb' }}>
        {onClose ? (
          <button type="button" onClick={onClose} style={lightButton}>닫기</button>
        ) : (
          <a href="/employment-contracts" style={{ ...lightButton, textDecoration: 'none' }}>← 근로계약</a>
        )}
        <button type="button" onClick={() => window.print()} style={lightButton}>인쇄</button>
        <span>A4 {pages.length}장 · 인쇄하면 이 크기 그대로 나갑니다.</span>
      </div>
      <div id="a4-print-area" style={{ padding: '16px 0' }}>
        <Pages pages={pages} title={title} />
      </div>
    </div>
  );
}

const barButton: CSSProperties = {
  background: '#111827',
  color: '#fff',
  border: 0,
  borderRadius: 6,
  padding: '6px 12px',
  fontWeight: 700,
  cursor: 'pointer',
};

const lightButton: CSSProperties = {
  ...barButton,
  background: '#fff',
  color: '#111827',
};
