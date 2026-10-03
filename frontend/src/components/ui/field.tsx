import * as React from 'react';
import { cn } from '@/lib/utils';

export function Field({
  label,
  hint,
  error,
  required,
  className,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn('form-group', className)}>
      <label>
        {label}
        {required ? <span className="field-required">*</span> : null}
      </label>
      {children}
      {error ? <p className="field-error">{error}</p> : hint ? <p className="field-help">{hint}</p> : null}
    </div>
  );
}
