import { Badge } from '../../ui/Badge'
import { count, dollars, seconds } from './summary'
import type { FullTrace } from './schema'

export function CallTable({ trace }: { trace: FullTrace }) {
  const calls = trace.llm_calls
  if (!calls.length) return null
  return (
    <section aria-labelledby="calls" className="mt-10">
      <h2 id="calls" className="text-xl font-semibold tracking-tight">
        Every model call
      </h2>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-3xl text-left text-sm">
          <thead className="text-xs text-muted">
            <tr className="border-b border-rule">
              <th className="py-2 pr-4 font-medium">Step</th>
              <th className="px-4 py-2 font-medium">Model</th>
              <th className="px-4 py-2 text-right font-medium">In / out</th>
              <th className="px-4 py-2 text-right font-medium">Time</th>
              <th className="px-4 py-2 text-right font-medium">Cost</th>
              <th className="py-2 pl-4 font-medium">Note</th>
            </tr>
          </thead>
          <tbody>
            {calls.map((call, index) => (
              <tr key={index} className="border-b border-rule/60 align-top">
                <td className="py-2 pr-4 font-mono text-xs">{call.step}</td>
                <td className="px-4 py-2 text-xs">{call.model ?? 'none'}</td>
                <td className="px-4 py-2 text-right">
                  {count(call.input_tokens)} / {count(call.output_tokens)}
                </td>
                <td className="px-4 py-2 text-right">
                  {call.latency_ms === null ? 'n/a' : seconds(call.latency_ms)}
                </td>
                <td className="px-4 py-2 text-right">{dollars(call.cost_usd)}</td>
                <td className="py-2 pl-4">
                  <span className="flex flex-wrap gap-1">
                    {call.cache_hit ? <Badge>cache</Badge> : null}
                    {call.failover_from ? (
                      <Badge tone="assumption">from {call.failover_from}</Badge>
                    ) : null}
                    {call.attempts && call.attempts > 1 ? (
                      <Badge tone="assumption">{count(call.attempts)} attempts</Badge>
                    ) : null}
                    {call.error ? <Badge tone="error">{call.error}</Badge> : null}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
