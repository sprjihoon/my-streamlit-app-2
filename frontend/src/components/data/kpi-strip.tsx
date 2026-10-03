import * as React from 'react';
import { Metric } from '@/components/ui/metric';

export function KpiStrip({
  items,
}: {
  items: { label: string; value: React.ReactNode; hint?: React.ReactNode }[];
}) {
  return (
    <div className="data-kpis">
      {items.map((item) => (
        <Metric
          key={item.label}
          label={item.label}
          value={
            <>
              {item.value}
              {item.hint ? <span className="data-kpi-hint">{item.hint}</span> : null}
            </>
          }
        />
      ))}
    </div>
  );
}
