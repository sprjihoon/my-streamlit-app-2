import * as React from 'react';
import { cn } from '@/lib/utils';

export function Field({
  label,
  className,
  labelClassName,
  children,
}: {
  label: string;
  className?: string;
  labelClassName?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn('tw-mb-4', className)}>
      <label className={cn('tw-mb-2 tw-block tw-font-medium', labelClassName)}>{label}</label>
      {children}
    </div>
  );
}
