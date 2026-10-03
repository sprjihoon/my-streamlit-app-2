import * as React from 'react';
import { cn } from '@/lib/utils';

export function DataSection({
  title,
  first,
  extra,
  tone,
  children,
  className,
}: {
  title: string;
  first?: boolean;
  extra?: React.ReactNode;
  tone?: 'sender' | 'recipient';
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn('ops-section', first && 'is-first', tone && `is-${tone}`, className)}>
      <div className="ops-section-head">
        <h3>{title}</h3>
        {extra}
      </div>
      {children}
    </section>
  );
}
