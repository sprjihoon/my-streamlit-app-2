import * as React from 'react';

export function FilterBar({
  children,
  trailing,
}: {
  children: React.ReactNode;
  trailing?: React.ReactNode;
}) {
  return (
    <div className="data-filter">
      <div className="data-filter-fields">{children}</div>
      {trailing ? <div className="data-filter-actions">{trailing}</div> : null}
    </div>
  );
}
