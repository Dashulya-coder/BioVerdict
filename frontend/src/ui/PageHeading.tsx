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
      <p className="mb-2 text-sm text-muted">{eyebrow}</p>
      <h1 className="font-editorial text-3xl leading-tight font-medium tracking-tight sm:text-4xl">
        {title}
      </h1>
      <p className="mt-3 text-[15px] leading-7 text-muted">{description}</p>
    </header>
  )
}
