import * as React from 'react';

export function TableSummary({ children }: { children: React.ReactNode }) {
  return <p className="data-summary">{children}</p>;
}
