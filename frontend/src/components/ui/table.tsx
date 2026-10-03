import * as React from 'react';
import { cn } from '@/lib/utils';

const Table = React.forwardRef<HTMLTableElement, React.HTMLAttributes<HTMLTableElement>>(
  ({ className, ...props }, ref) => (
    <div className="table-container">
      <table ref={ref} className={className} {...props} />
    </div>
  ),
);
Table.displayName = 'Table';

const TableHeader = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => <thead ref={ref} className={className} {...props} />,
);
TableHeader.displayName = 'TableHeader';

const TableBody = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => <tbody ref={ref} className={className} {...props} />,
);
TableBody.displayName = 'TableBody';

const TableRow = React.forwardRef<HTMLTableRowElement, React.HTMLAttributes<HTMLTableRowElement>>(
  ({ className, ...props }, ref) => <tr ref={ref} className={className} {...props} />,
);
TableRow.displayName = 'TableRow';

const TableHead = React.forwardRef<HTMLTableCellElement, React.ThHTMLAttributes<HTMLTableCellElement> & { numeric?: boolean }>(
  ({ className, numeric, ...props }, ref) => <th ref={ref} className={cn(numeric && 'cell-num', className)} {...props} />,
);
TableHead.displayName = 'TableHead';

const TableCell = React.forwardRef<HTMLTableCellElement, React.TdHTMLAttributes<HTMLTableCellElement> & { numeric?: boolean; truncate?: boolean }>(
  ({ className, numeric, truncate, ...props }, ref) => (
    <td ref={ref} className={cn(numeric && 'cell-num', truncate && 'cell-truncate', className)} {...props} />
  ),
);
TableCell.displayName = 'TableCell';

export { Table, TableHeader, TableBody, TableRow, TableHead, TableCell };
