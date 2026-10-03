import * as React from 'react';
import { cn } from '@/lib/utils';

export function Alert({
  type,
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & {
  type: 'success' | 'warning' | 'error' | 'info';
}) {
  return <div className={cn('alert', `alert-${type}`, 'tw-relative')} {...props} />;
}
