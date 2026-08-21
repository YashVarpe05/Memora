import { cva, type VariantProps } from 'class-variance-authority';
import type { ButtonHTMLAttributes } from 'react';

import { cn } from '@/lib/utils';

const button = cva(
  'inline-flex items-center justify-center gap-2 rounded-lg font-medium ' +
    'transition-colors disabled:pointer-events-none disabled:opacity-50 ' +
    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
  {
    variants: {
      variant: {
        primary: 'bg-accent text-accent-ink hover:opacity-90',
        subtle: 'bg-surface-sunken text-ink hover:bg-line',
        ghost: 'text-ink-muted hover:bg-surface-sunken hover:text-ink',
      },
      size: {
        // 44px minimum - thumb-reachable, per the mobile-first rule.
        md: 'h-11 px-4 text-sm',
        icon: 'size-11 shrink-0',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
);

type Props = ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof button>;

export function Button({ className, variant, size, ...props }: Props) {
  return <button className={cn(button({ variant, size }), className)} {...props} />;
}
