import { Badge } from '../../ui/Badge'
import { diligence } from './diligence'
import type { Report } from './schema'

/** The questions to ask next, the one that would change the decision most first. */
export function DiligenceQuestions({ report }: { report: Report }) {
  const questions = [...report.diligence_questions].sort(
    (a, b) => b.value_of_information - a.value_of_information,
  )
  return (
    <section aria-labelledby="questions" className="mt-10">
      <h2 id="questions" className="font-editorial text-2xl">
        Questions to ask next
      </h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
        Ranked by the value of the answer: how far it could move the verdict.
      </p>
      {questions.length ? (
        <ol className="mt-5 max-w-3xl space-y-3">
          {questions.map((question, index) => (
            <li key={question.text} className="flex gap-4 border border-rule bg-surface p-4">
              <span className="font-mono text-xs text-muted">{(index + 1).toString()}</span>
              <div>
                <p className="text-sm leading-6">{question.text}</p>
                <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
                  <Badge tone="assumption">
                    {diligence[question.answered_by]?.label ?? 'Open question'}
                  </Badge>
                  Value of information {question.value_of_information.toFixed(2)}
                </p>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-4 max-w-2xl text-sm text-muted">
          No question was ranked for this run: the Chair step proposed none, or it did not finish.
        </p>
      )}
    </section>
  )
}
