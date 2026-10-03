import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva('tw-inline-flex tw-items-center', {
  variants: {
    variant: {
      role: 'tw-mt-px tw-text-[0.7rem] tw-font-normal tw-normal-case tw-tracking-normal tw-text-white/45',
      success: 'tw-rounded-[var(--radius-sm)] tw-bg-[#f0fdf4] tw-px-2 tw-py-0.5 tw-text-[0.75rem] tw-font-semibold tw-text-[#166534]',
      warning: 'tw-rounded-[var(--radius-sm)] tw-bg-[#fffbeb] tw-px-2 tw-py-0.5 tw-text-[0.75rem] tw-font-semibold tw-text-[#92400e]',
      danger: 'tw-rounded-[var(--radius-sm)] tw-bg-[#fef2f2] tw-px-2 tw-py-0.5 tw-text-[0.75rem] tw-font-semibold tw-text-[#991b1b]',
      info: 'tw-rounded-[var(--radius-sm)] tw-bg-[#eff6ff] tw-px-2 tw-py-0.5 tw-text-[0.75rem] tw-font-semibold tw-text-[#1e40af]',
    },
  },
  defaultVariants: {
    variant: 'info',
  },
});

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
