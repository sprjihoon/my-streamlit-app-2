import * as React from 'react';
import { cn } from '@/lib/utils';

export function ActionBar({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn('ops-actions', className)}>{children}</div>;
}
