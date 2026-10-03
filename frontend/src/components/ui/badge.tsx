import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva('tw-inline-flex tw-items-center tw-rounded-full tw-px-2 tw-py-[2px] tw-text-[11px] tw-font-semibold', {
  variants: {
    variant: {
      success: 'tw-bg-[#e8f7ee] tw-text-[#157347]',
      warning: 'tw-bg-[#fff6e5] tw-text-[#9a6700]',
      danger: 'tw-bg-[#fdecec] tw-text-[#b42318]',
      info: 'tw-bg-[#eef2ff] tw-text-[#3451d1]',
      neutral: 'tw-bg-[#f3f4f8] tw-text-[#4b5163]',
    },
  },
  defaultVariants: {
    variant: 'neutral',
  },
});

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
