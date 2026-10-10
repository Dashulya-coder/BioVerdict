import type { ReactNode } from 'react'
import { showPart } from './showClaim'
import { thesisTitles } from './thesisTitles'

/** The parts of the underwriting report in the order the brief lists them, then the rest. */
const brief: { target: string; label: string }[] = [
  { target: 'executive', label: 'Recommendation' },
  { target: 'thesis-scientific', label: thesisTitles.scientific },
  { target: 'thesis-translation', label: thesisTitles.translation },
  { target: 'thesis-development_plan', label: thesisTitles.development_plan },
  { target: 'thesis-competitive', label: thesisTitles.competitive },
  { target: 'thesis-commercial', label: thesisTitles.commercial },
  { target: 'capital', label: 'Capital required to reach the next major milestone' },
  { target: 'thesis-investment', label: thesisTitles.investment },
  { target: 'risks', label: 'Key risks and failure modes' },
  { target: 'unknowns', label: 'Critical unknowns' },
  { target: 'questions', label: 'Highest-value diligence questions' },
  { target: 'sources', label: 'Sources supporting major claims' },
]
const more: { target: string; label: string }[] = [
  { target: 'modules', label: 'Six modules, six answers' },
  { target: 'gates', label: 'Gates' },
  { target: 'chain', label: 'Translation chain' },
  { target: 'tornado', label: 'What moves the rNPV' },
  { target: 'claims', label: 'All claims and their evidence' },
]

/** A part this run does not have (a thesis the synthesis step did not write) falls back to
 * the written case as a whole. */
function Jump({ target, children }: { target: string; children: ReactNode }) {
  return (
    <a
      href={`#${target}`}
      onClick={(event) => {
        event.preventDefault()
        showPart(target, 'theses')
      }}
      className="text-muted underline-offset-4 hover:text-ink hover:underline"
    >
      {children}
    </a>
  )
}

export function Contents() {
  return (
    <nav aria-label="Contents of the report" className="mt-8 border-y border-rule py-5 text-sm">
      <ol className="grid gap-x-8 gap-y-1.5 sm:grid-cols-2 xl:grid-cols-3">
        {brief.map((item, index) => (
          <li key={item.target}>
            <Jump target={item.target}>
              <span className="mr-2 inline-block w-5 text-right tabular-nums">
                {(index + 1).toString()}
              </span>
              {item.label}
            </Jump>
          </li>
        ))}
      </ol>
      <p className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-1 text-muted">
        Also:
        {more.map((item) => (
          <Jump key={item.target} target={item.target}>
            {item.label}
          </Jump>
        ))}
      </p>
    </nav>
  )
}
