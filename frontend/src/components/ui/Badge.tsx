import type { ReactNode } from 'react';

interface BadgeProps {
  children: ReactNode;
  variant?: 'success' | 'danger' | 'warning' | 'neutral' | 'info';
  className?: string;
}

const variants: Record<NonNullable<BadgeProps['variant']>, string> = {
  success: 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/25',
  danger: 'bg-red-500/15 text-red-400 ring-red-500/25',
  warning: 'bg-amber-500/15 text-amber-400 ring-amber-500/25',
  neutral: 'bg-zinc-500/15 text-zinc-400 ring-zinc-500/25',
  info: 'bg-blue-500/15 text-blue-400 ring-blue-500/25',
};

export function Badge({ children, variant = 'neutral', className = '' }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${variants[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
