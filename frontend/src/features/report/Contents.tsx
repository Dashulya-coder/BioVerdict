import { thesisTitles } from './thesisTitles'

/** The parts of the underwriting report in the order the brief lists them, then the rest. */
const brief: { href: string; label: string }[] = [
  { href: '#executive', label: 'Recommendation' },
  { href: '#thesis-scientific', label: thesisTitles.scientific },
  { href: '#thesis-translation', label: thesisTitles.translation },
  { href: '#thesis-development_plan', label: thesisTitles.development_plan },
  { href: '#thesis-competitive', label: thesisTitles.competitive },
  { href: '#thesis-commercial', label: thesisTitles.commercial },
  { href: '#capital', label: 'Capital required to reach the next major milestone' },
  { href: '#thesis-investment', label: thesisTitles.investment },
  { href: '#risks', label: 'Key risks and failure modes' },
  { href: '#unknowns', label: 'Critical unknowns' },
  { href: '#questions', label: 'Highest-value diligence questions' },
  { href: '#sources', label: 'Sources supporting major claims' },
]
const more: { href: string; label: string }[] = [
  { href: '#modules', label: 'Six modules, six answers' },
  { href: '#gates', label: 'Gates' },
  { href: '#chain', label: 'Translation chain' },
  { href: '#tornado', label: 'What moves the rNPV' },
  { href: '#claims', label: 'All claims and their evidence' },
]

export function Contents() {
  return (
    <nav aria-label="Contents of the report" className="mb-8 text-sm">
      <ol className="flex flex-wrap gap-x-4 gap-y-1">
        {brief.map((item, index) => (
          <li key={item.href}>
            <a href={item.href} className="text-accent underline-offset-2 hover:underline">
              <span className="mr-1 font-mono text-xs text-muted">{(index + 1).toString()}</span>
              {item.label}
            </a>
          </li>
        ))}
      </ol>
      <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        Also:
        {more.map((item) => (
          <a key={item.href} href={item.href} className="underline-offset-2 hover:underline">
            {item.label}
          </a>
        ))}
      </p>
    </nav>
  )
}
