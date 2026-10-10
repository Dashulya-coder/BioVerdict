export function PageHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string
  title: string
  description: string
}) {
  return (
    <header className="mb-8 max-w-3xl">
      <p className="mb-3 flex items-center gap-2 font-mono text-[11px] tracking-[0.18em] text-accent uppercase">
        <span aria-hidden="true" className="h-px w-6 bg-accent/60" />
        {eyebrow}
      </p>
      <h1 className="font-editorial text-3xl leading-tight font-medium tracking-tight sm:text-[2.5rem]">
        {title}
      </h1>
      <p className="mt-3 text-[15px] leading-7 text-muted">{description}</p>
    </header>
  )
}
