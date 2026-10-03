import * as React from 'react';
import { cn } from '@/lib/utils';

const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => {
    return <textarea className={cn('ui-control', className)} ref={ref} {...props} />;
  },
);
Textarea.displayName = 'Textarea';

export { Textarea };
