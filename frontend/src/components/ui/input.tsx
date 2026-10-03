import * as React from 'react';
import { cn } from '@/lib/utils';

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => {
    return <input className={cn('ui-control', className)} ref={ref} {...props} />;
  },
);
Input.displayName = 'Input';

export { Input };
