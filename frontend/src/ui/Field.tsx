import type { InputHTMLAttributes } from 'react'

type Props = InputHTMLAttributes<HTMLInputElement> & {
  id: string
  label: string
  hint?: string
  error?: string
}

export function Field({ id, label, hint, error, className = '', ...props }: Props) {
  const descriptionId = hint || error ? `${id}-description` : undefined
  return (
    <div className="space-y-2">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <input
        {...props}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={descriptionId}
        className={`min-h-11 w-full rounded-sm border bg-sidebar px-3 py-2.5 text-sm placeholder:text-muted ${error ? 'border-danger' : 'border-control'} ${className}`}
      />
      {hint || error ? (
        <p
          id={descriptionId}
          className={`text-xs leading-5 ${error ? 'text-danger' : 'text-muted'}`}
        >
          {error ?? hint}
        </p>
      ) : null}
    </div>
  )
}
