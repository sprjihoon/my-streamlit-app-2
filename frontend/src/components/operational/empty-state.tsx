import * as React from 'react';
import { cn } from '@/lib/utils';

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: string;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('ops-empty', className)}>
      {icon ? <div className="ops-empty-icon">{icon}</div> : null}
      <div className="ops-empty-title">{title}</div>
      {description ? <div className="ops-empty-copy">{description}</div> : null}
      {action}
    </div>
  );
}
