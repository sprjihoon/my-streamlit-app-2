'use client';

import { useEffect } from 'react';

const PRINT_STYLE = `
.a4-preview-root { background: #d1d5db; min-height: 100%; }
.a4-preview-bar {
  position: sticky; top: 0; z-index: 2;
  display: flex; align-items: center; gap: 12px;
  background: #111827; color: #e5e7eb;
  padding: 8px 16px; font-size: 13px;
}
.a4-preview-bar button, .a4-preview-bar a {
  background: #fff; color: #111827; border: 0; border-radius: 6px;
  padding: 6px 12px; font-weight: 700; cursor: pointer; text-decoration: none;
}
.a4-sheet {
  width: 210mm; height: 297mm; margin: 16px auto;
  background: #fff; box-shadow: 0 8px 24px rgba(0,0,0,.18); overflow: hidden;
}
.a4-sheet img { width: 100%; height: 100%; object-fit: fill; display: block; }
@media print {
  .a4-preview-bar { display: none !important; }
  body * { visibility: hidden !important; }
  #a4-print-area, #a4-print-area * { visibility: visible !important; }
  #a4-print-area { position: absolute; left: 0; top: 0; width: 210mm; background: #fff; }
  .a4-sheet { margin: 0; box-shadow: none; page-break-after: always; break-after: page; }
  @page { size: A4 portrait; margin: 0; }
}
`;

export function A4Preview({
  pages,
  onClose,
  overlay = false,
}: {
  pages: string[];
  onClose?: () => void;
  overlay?: boolean;
}) {
  useEffect(() => {
    const style = document.createElement('style');
    style.setAttribute('data-a4-preview', '1');
    style.textContent = PRINT_STYLE;
    document.head.appendChild(style);
    return () => style.remove();
  }, []);

  return (
    <div
      className="a4-preview-root"
      style={overlay ? { position: 'fixed', inset: 0, zIndex: 80, overflow: 'auto' } : { minHeight: '100vh' }}
    >
      <div className="a4-preview-bar">
        {onClose ? (
          <button type="button" onClick={onClose}>닫기</button>
        ) : (
          <a href="/employment-contracts">← 근로계약</a>
        )}
        <button type="button" onClick={() => window.print()}>인쇄</button>
        <span>A4 {pages.length}장 · 인쇄하면 이 크기 그대로 나갑니다.</span>
      </div>
      <div id="a4-print-area">
        {pages.map((page, index) => (
          <div className="a4-sheet" key={index}>
            <img
              src={page.startsWith('data:') ? page : `data:image/png;base64,${page}`}
              alt={`근로계약서 ${index + 1}쪽`}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
