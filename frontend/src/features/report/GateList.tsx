import { Badge } from '../../ui/Badge'
import type { Report } from './schema'

const conditions: Record<string, string> = {
  K1: 'The same target failed in Phase 2/3 for efficacy in this indication',
  K2: 'Serious on-target toxicity in humans with no way to mitigate it',
  K3: 'Human genetics contradicts the direction of action',
  K4: 'The sponsor stopped the program',
  K5: 'rNPV is negative even in the optimistic scenario',
  S1: 'A link of the translation chain is missing',
  S2: 'Key claims are sparse',
  S3: 'A key claim is contested',
  S4: 'Three or more same-mechanism competitors are a phase ahead',
  S5: 'The biomarker or endpoint is not a recognised surrogate',
  S6: 'IP ends soon after launch, or ownership is unclear',
}

/** Every gate the rule checks: which fired, which nearly did, and the claims behind each. */
export function GateList({ report }: { report: Report }) {
  const hard = report.gates.filter((gate) => gate.kind === 'hard')
  const soft = report.gates.filter((gate) => gate.kind === 'soft')
  return (
    <section aria-labelledby="gates" className="mt-10">
      <h2 id="gates" className="font-editorial text-2xl">
        Gates
      </h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
        Code applies these rules to the claims. A hard gate that fires means Do Not Invest; a soft
        gate caps the verdict at Conditional.
      </p>
      <div className="mt-5 grid gap-6 md:grid-cols-2">
        <GateGroup title="Hard gates" gates={hard} />
        <GateGroup title="Soft gates" gates={soft} />
      </div>
    </section>
  )
}

function GateGroup({ title, gates }: { title: string; gates: Report['gates'] }) {
  return (
    <div>
      <h3 className="text-sm font-medium">{title}</h3>
      <ul className="mt-3 space-y-2">
        {gates.map((gate) => (
          <li
            key={gate.gate_id}
            className={`border bg-surface p-3 text-sm leading-6 ${gate.fired ? 'border-danger/40' : 'border-rule'}`}
          >
            <p className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs">{gate.gate_id}</span>
              {gate.fired ? (
                <Badge tone="error">Fired</Badge>
              ) : gate.near_miss ? (
                <Badge tone="assumption">Near miss</Badge>
              ) : (
                <Badge>Clear</Badge>
              )}
              <span className={gate.fired ? '' : 'text-muted'}>
                {conditions[gate.gate_id] ?? 'Gate condition'}
              </span>
            </p>
            {gate.near_miss ? <p className="mt-1 text-xs text-muted">{gate.near_miss}</p> : null}
            {gate.claim_ids.length ? (
              <p className="mt-1 font-mono text-xs text-muted">
                Claims: {gate.claim_ids.join(', ')}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}
