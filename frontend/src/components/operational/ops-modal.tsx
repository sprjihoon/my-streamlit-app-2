import * as React from 'react';

export function OpsModal({
  title,
  onClose,
  children,
  wide,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="ops-modal-backdrop">
      <div className={wide ? 'ops-modal is-wide' : 'ops-modal'}>
        <div className="ops-modal-head">
          <h2>{title}</h2>
          <button type="button" className="ops-modal-close" onClick={onClose} aria-label="닫기">
            ×
          </button>
        </div>
        <div className="ops-modal-body">{children}</div>
      </div>
    </div>
  );
}
