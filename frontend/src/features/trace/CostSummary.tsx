import { Badge } from '../../ui/Badge'
import { count, dollars, modelsUsed } from './summary'
import type { FullTrace } from './schema'

export function CostSummary({ trace }: { trace: FullTrace }) {
  const { totals, llm_calls: calls } = trace
  const models = modelsUsed(calls)
  const cached = calls.filter((call) => call.cache_hit).length
  const failedOver = calls.filter((call) => call.failover_from).length
  return (
    <section aria-labelledby="cost" className="border-y border-rule py-8">
      <h2 id="cost" className="sr-only">
        Cost of the run
      </h2>
      <dl className="grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-4">
        <div className="border-l border-rule pl-4">
          <dt className="text-xs text-muted">Cost</dt>
          <dd className="font-editorial text-3xl">{dollars(totals.cost_usd)}</dd>
        </div>
        <div className="border-l border-rule pl-4">
          <dt className="text-xs text-muted">Model calls</dt>
          <dd className="font-editorial text-3xl">{count(totals.calls)}</dd>
          <dd className="text-xs text-muted">{count(cached)} from the cache</dd>
        </div>
        <div className="border-l border-rule pl-4">
          <dt className="text-xs text-muted">Tokens in</dt>
          <dd className="font-editorial text-3xl">{count(totals.input_tokens)}</dd>
        </div>
        <div className="border-l border-rule pl-4">
          <dt className="text-xs text-muted">Tokens out</dt>
          <dd className="font-editorial text-3xl">{count(totals.output_tokens)}</dd>
        </div>
      </dl>
      <p className="mt-6 flex flex-wrap items-center gap-2 text-sm text-muted">
        {models.length ? `Answered by ${models.join(', ')}.` : 'No model answered afresh.'}
        {models.length > 1 || failedOver ? (
          <Badge tone="assumption">
            Mixed models{failedOver ? `: ${count(failedOver)} calls failed over` : ''}
          </Badge>
        ) : null}
      </p>
    </section>
  )
}
