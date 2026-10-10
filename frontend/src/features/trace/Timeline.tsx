import { Badge } from '../../ui/Badge'
import type { FullTrace } from './schema'

const tone = (status: string) =>
  status === 'failed' ? 'error' : status === 'done' ? 'fact' : 'neutral'

export function Timeline({ trace }: { trace: FullTrace }) {
  return (
    <section aria-labelledby="timeline" className="mt-10">
      <h2 id="timeline" className="text-xl font-semibold tracking-tight">
        Steps in order
      </h2>
      {trace.events.length ? (
        <ol className="mt-4 space-y-2 text-sm">
          {trace.events.map((event) => (
            <li key={event.seq} className="flex flex-wrap items-baseline gap-x-3">
              <span className="font-mono text-xs">{event.step}</span>
              <Badge tone={tone(event.status)}>{event.status}</Badge>
              {event.detail ? <span className="text-muted">{event.detail}</span> : null}
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-3 text-sm text-muted">No step has been recorded yet.</p>
      )}
    </section>
  )
}
