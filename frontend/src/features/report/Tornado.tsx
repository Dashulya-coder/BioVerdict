import { useEffect, useState } from 'react'
import { Badge } from '../../ui/Badge'
import { fetchFinancials } from './financials'
import { money } from './numbers'
import type { Financials } from './financials'

type State = { kind: 'loading' } | { kind: 'error' } | { kind: 'ready'; financials: Financials }

/** Which input moves the rNPV the most, one input at a time. The inputs are labeled as modeled. */
export function Tornado({ runId }: { runId: string }) {
  const [loaded, setLoaded] = useState<{ runId: string; state: State } | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    fetchFinancials(runId, controller.signal)
      .then((financials) => {
        setLoaded({ runId, state: { kind: 'ready', financials } })
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoaded({ runId, state: { kind: 'error' } })
      })
    return () => {
      controller.abort()
    }
  }, [runId])
  const state: State = loaded?.runId === runId ? loaded.state : { kind: 'loading' }
  return (
    <section aria-labelledby="tornado" className="mt-10">
      <h2 id="tornado" className="font-editorial text-2xl">
        What moves the rNPV
      </h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
        Each bar moves one input from its low to its high end while the others stay at their base.
        The inputs are placeholders until they are calibrated on sources: read the order of the
        bars, not the dollars.
      </p>
      {state.kind === 'loading' ? (
        <p role="status" className="mt-4 text-sm text-muted">
          Loading the sensitivity…
        </p>
      ) : state.kind === 'error' ? (
        <p className="mt-4 text-sm text-muted">The sensitivity could not be loaded.</p>
      ) : state.financials.tornado.length ? (
        <Bars financials={state.financials} />
      ) : (
        <p className="mt-4 text-sm text-muted">
          Not computed: {state.financials.missing.join(' ') || 'no rNPV for this run.'}
        </p>
      )}
    </section>
  )
}

const label = (input: string) => input.replaceAll('_', ' ')

function Bars({ financials }: { financials: Financials }) {
  const bars = financials.tornado
  const low = Math.min(0, ...bars.flatMap((bar) => [bar.at_low, bar.at_high]))
  const high = Math.max(0, ...bars.flatMap((bar) => [bar.at_low, bar.at_high]))
  const span = high - low || 1
  const at = (value: number) => ((value - low) / span) * 100
  return (
    <ul className="mt-5 space-y-3">
      {bars.map((bar) => {
        const left = Math.min(bar.at_low, bar.at_high)
        const right = Math.max(bar.at_low, bar.at_high)
        return (
          <li
            key={bar.input}
            className="grid items-center gap-x-4 gap-y-1 text-sm md:grid-cols-[12rem_1fr]"
          >
            <span className="capitalize">{label(bar.input)}</span>
            <span className="grid grid-cols-[4.5rem_1fr_4.5rem] items-center gap-2">
              <span className="text-right font-mono text-xs text-muted">{money(left)}</span>
              <span className="relative block h-4 bg-surface" aria-hidden="true">
                <span
                  className="absolute inset-y-0 bg-assumption/60"
                  style={{
                    left: `${at(left).toString()}%`,
                    width: `${(at(right) - at(left)).toString()}%`,
                  }}
                />
                <span
                  className="absolute inset-y-[-2px] w-px bg-ink"
                  style={{ left: `${at(0).toString()}%` }}
                />
              </span>
              <span className="font-mono text-xs text-muted">{money(right)}</span>
            </span>
          </li>
        )
      })}
      <li className="pt-1">
        <Badge tone="assumption">Modeled</Badge>
        <span className="ml-2 text-xs text-muted">The line marks an rNPV of zero.</span>
      </li>
    </ul>
  )
}
