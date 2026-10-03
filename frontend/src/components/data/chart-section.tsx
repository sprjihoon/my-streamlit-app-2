import * as React from 'react';

export function ChartSection({
  title,
  description,
  extra,
  children,
}: {
  title: string;
  description?: React.ReactNode;
  extra?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="card">
      <div className="surface-header">
        <h2>{title}</h2>
        {extra}
      </div>
      {description ? <p className="caption tw-mb-2">{description}</p> : null}
      {children}
    </section>
  );
}
