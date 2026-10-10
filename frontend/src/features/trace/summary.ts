import type { TraceCall } from './schema'

export interface StepCost {
  step: string
  calls: number
  cached: number
  failed: number
  tokens: number
  cost: number
  latencyMs: number
}

/** The model calls of a run added up by the step that made them, in the order the steps began. */
export function byStep(calls: readonly TraceCall[]): StepCost[] {
  const steps = new Map<string, StepCost>()
  for (const call of calls) {
    const step = steps.get(call.step) ?? {
      step: call.step,
      calls: 0,
      cached: 0,
      failed: 0,
      tokens: 0,
      cost: 0,
      latencyMs: 0,
    }
    step.calls += 1
    step.cached += call.cache_hit ? 1 : 0
    step.failed += call.error ? 1 : 0
    step.tokens += call.input_tokens + call.output_tokens
    step.cost += call.cost_usd
    step.latencyMs += call.latency_ms ?? 0
    steps.set(call.step, step)
  }
  return [...steps.values()]
}

/** The models that actually answered; more than one means the run is `mixed_models`. */
export function modelsUsed(calls: readonly TraceCall[]): string[] {
  return [...new Set(calls.flatMap((call) => (call.model && !call.cache_hit ? [call.model] : [])))]
}

export const dollars = (value: number): string =>
  value < 0.01 && value > 0 ? '<$0.01' : `$${value.toFixed(2)}`

export const seconds = (ms: number): string => `${(ms / 1000).toFixed(1)} s`

export const count = (value: number): string => value.toLocaleString('en-US')
