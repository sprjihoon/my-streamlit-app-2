import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const inputVariants = cva('tw-w-full tw-font-[inherit]', {
  variants: {
    tone: {
      plain: 'tw-rounded-[4px] tw-border tw-border-solid tw-border-[#dee2e6] tw-bg-white tw-px-[0.6rem] tw-py-[0.6rem]',
      form: 'tw-rounded-[var(--radius-sm)] tw-border-[1.5px] tw-border-solid tw-border-tillion-border tw-bg-white tw-px-3 tw-py-[0.55rem] tw-text-[0.875rem] tw-text-tillion-text focus:tw-border-[var(--border-focus)] focus:tw-shadow-[0_0_0_3px_rgba(67,97,238,0.12)] focus:tw-outline-none',
    },
  },
  defaultVariants: {
    tone: 'plain',
  },
});

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement>,
    VariantProps<typeof inputVariants> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, tone, ...props }, ref) => {
    return <input className={cn(inputVariants({ tone }), className)} ref={ref} {...props} />;
  },
);
Input.displayName = 'Input';

export { Input, inputVariants };
