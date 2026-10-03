import * as React from 'react';
import { cn } from '@/lib/utils';

export function Metric({
  value,
  label,
  valueClassName,
}: {
  value: React.ReactNode;
  label: React.ReactNode;
  valueClassName?: string;
}) {
  return (
    <div className="metric">
      <div className={cn('metric-value', valueClassName)}>{value}</div>
      <div className="metric-label">{label}</div>
    </div>
  );
}
