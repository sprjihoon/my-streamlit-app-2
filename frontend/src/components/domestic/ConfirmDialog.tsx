'use client';

import type { ReactNode } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  confirmClass,
  busy,
  busyLabel,
  onDismiss,
  onConfirm,
  children,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  confirmClass: string;
  busy?: boolean;
  busyLabel?: string;
  onDismiss: () => void;
  onConfirm: () => void;
  children?: ReactNode;
}) {
  return (
    <Dialog open={open} onOpenChange={(next: boolean) => { if (!next && !busy) onDismiss(); }}>
      <DialogContent className="domestic-dialog">
        <DialogTitle className="domestic-dialog-title">{title}</DialogTitle>
        <DialogDescription className="domestic-dialog-copy">{description}</DialogDescription>
        {children}
        <div className="domestic-actions">
          <button type="button" className="btn btn-secondary" disabled={busy} onClick={onDismiss}>
            취소
          </button>
          <button type="button" className={confirmClass} disabled={busy} onClick={onConfirm}>
            {busy ? (busyLabel || '처리 중...') : confirmLabel}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
