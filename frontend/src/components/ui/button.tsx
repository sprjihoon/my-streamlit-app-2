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
        ghost: 'btn btn-ghost',
        destructive: 'btn btn-danger',
        icon: 'btn btn-icon',
        success: 'btn btn-success',
        danger: 'btn btn-danger',
        warning: 'btn btn-warning',
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
