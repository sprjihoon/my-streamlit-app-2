import * as React from 'react';
import { cn } from '@/lib/utils';

const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, ...props }, ref) => {
    return <select className={cn('ui-control', className)} ref={ref} {...props} />;
  },
);
Select.displayName = 'Select';

export { Select };
