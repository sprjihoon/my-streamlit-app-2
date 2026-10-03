import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'tw-inline-flex tw-cursor-pointer tw-items-center tw-justify-center tw-font-[inherit] disabled:tw-cursor-not-allowed',
  {
    variants: {
      variant: {
        primary: 'btn btn-primary',
        secondary: 'btn btn-secondary',
        success: 'btn btn-success',
        danger: 'btn btn-danger',
        warning: 'btn btn-warning',
        sidebarPrimary:
          'tw-flex-1 tw-gap-[0.3rem] tw-rounded-[5px] tw-border-0 tw-bg-[rgba(67,97,238,0.7)] tw-px-[0.4rem] tw-py-[0.3rem] tw-text-[0.72rem] tw-font-semibold tw-text-white',
        sidebarMuted:
          'tw-flex-1 tw-gap-[0.3rem] tw-rounded-[5px] tw-border tw-border-solid tw-border-white/15 tw-bg-white/10 tw-px-[0.4rem] tw-py-[0.3rem] tw-text-[0.72rem] tw-font-semibold tw-text-white/75',
        sidebarLogout:
          'tw-w-full tw-rounded-[6px] tw-border tw-border-solid tw-border-white/15 tw-bg-white/10 tw-py-[0.4rem] tw-text-[0.8rem] tw-text-white/75',
        forcedSubmit:
          'tw-w-full tw-rounded-[6px] tw-border-0 tw-bg-[#0d6efd] tw-py-3 tw-font-semibold tw-text-white disabled:tw-bg-[#ccc]',
        changeSubmit:
          'tw-flex-1 tw-rounded-[4px] tw-border-0 tw-bg-[#4CAF50] tw-p-2 tw-text-white disabled:tw-bg-[#ccc]',
        cancel:
          'tw-flex-1 tw-rounded-[4px] tw-border-0 tw-bg-[#9e9e9e] tw-p-2 tw-text-white',
      },
    },
    defaultVariants: {
      variant: 'primary',
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return <Comp className={cn(buttonVariants({ variant }), className)} ref={ref} {...props} />;
  },
);
Button.displayName = 'Button';

export { Button, buttonVariants };
