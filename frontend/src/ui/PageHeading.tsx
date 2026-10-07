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
    <header className="mb-8 max-w-2xl">
      <p className="mb-3 font-mono text-xs tracking-[0.16em] text-accent uppercase">{eyebrow}</p>
      <h1 className="font-editorial text-3xl leading-tight font-medium sm:text-4xl">{title}</h1>
      <p className="mt-3 text-sm leading-7 text-muted">{description}</p>
    </header>
  )
}
