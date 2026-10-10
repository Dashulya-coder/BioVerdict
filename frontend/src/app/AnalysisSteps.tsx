const steps = ['Input', 'Resolve', 'Evidence'] as const

export function AnalysisSteps({ active }: { active: 0 | 1 | 2 }) {
  return (
    <ol aria-label="Analysis steps" className="mb-8 flex flex-wrap gap-4 border-y border-rule py-4">
      {steps.map((label, index) => (
        <li
          key={label}
          aria-current={index === active ? 'step' : undefined}
          className={`flex items-center gap-2 text-xs ${index <= active ? 'text-ink' : 'text-muted'}`}
        >
          <span
            className={`flex size-5 items-center justify-center rounded-full border font-mono text-[10px] ${index <= active ? 'border-control bg-raised' : 'border-rule'}`}
          >
            {index + 1}
          </span>
          {label}
          {index < steps.length - 1 ? (
            <span aria-hidden="true" className="ml-3 hidden h-px w-10 bg-rule sm:block" />
          ) : null}
        </li>
      ))}
    </ol>
  )
}
