import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost'
const variants: Record<Variant, string> = {
  primary: 'border-accent bg-accent text-sidebar hover:bg-accent/90',
  secondary: 'border-rule bg-surface text-ink hover:bg-raised',
  ghost: 'border-transparent text-muted hover:bg-surface hover:text-ink',
}
type Props = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }

export function Button({ variant = 'primary', className = '', type = 'button', ...props }: Props) {
  return (
    <button
      {...props}
      type={type}
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-sm border px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${variants[variant]} ${className}`}
    />
  )
}
