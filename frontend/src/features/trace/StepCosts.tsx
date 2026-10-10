import { Badge } from '../../ui/Badge'
import { byStep, count, dollars, seconds } from './summary'
import type { FullTrace } from './schema'

export function StepCosts({ trace }: { trace: FullTrace }) {
  const steps = byStep(trace.llm_calls)
  return (
    <section aria-labelledby="steps" className="mt-10">
      <h2 id="steps" className="font-editorial text-2xl">
        Cost by step
      </h2>
      {steps.length ? (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-xl text-left text-sm">
            <thead className="text-xs text-muted">
              <tr className="border-b border-rule">
                <th className="py-2 pr-4 font-medium">Step</th>
                <th className="px-4 py-2 text-right font-medium">Calls</th>
                <th className="px-4 py-2 text-right font-medium">Tokens</th>
                <th className="px-4 py-2 text-right font-medium">Time</th>
                <th className="py-2 pl-4 text-right font-medium">Cost</th>
              </tr>
            </thead>
            <tbody>
              {steps.map((step) => (
                <tr key={step.step} className="border-b border-rule/60">
                  <td className="py-2 pr-4 font-mono text-xs">
                    {step.step}{' '}
                    {step.failed ? <Badge tone="error">{count(step.failed)} failed</Badge> : null}
                  </td>
                  <td className="px-4 py-2 text-right">
                    {count(step.calls)}
                    {step.cached ? (
                      <span className="text-xs text-muted"> ({count(step.cached)} cached)</span>
                    ) : null}
                  </td>
                  <td className="px-4 py-2 text-right">{count(step.tokens)}</td>
                  <td className="px-4 py-2 text-right">{seconds(step.latencyMs)}</td>
                  <td className="py-2 pl-4 text-right">{dollars(step.cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="mt-3 text-sm text-muted">This run has made no model call yet.</p>
      )}
    </section>
  )
}
