import { Badge } from '../../ui/Badge'
import { Button } from '../../ui/Button'
import { Icon } from '../../ui/Icon'
import { PageHeading } from '../../ui/PageHeading'
import { AnalysisSteps } from '../../app/AnalysisSteps'
import type { PreparedAnalysis } from '../../app/models'

export function ResolvedInput({
  analysis,
  onBack,
  onContinue,
}: {
  analysis: PreparedAnalysis
  onBack: () => void
  onContinue: () => void
}) {
  const resolver = analysis.resolver
  const rows = [
    { label: 'Drug', value: analysis.input.asset, field: 'known_assets' },
    { label: 'Indication', value: resolver.indication.name, field: 'indication' },
    {
      label: 'Target',
      value: resolver.targets.map((target) => target.symbol).join(', '),
      field: 'targets',
    },
    { label: 'Action', value: resolver.action, field: 'action' },
    { label: 'Modality', value: resolver.modality, field: 'modality' },
    { label: 'Delivery', value: resolver.delivery, field: 'delivery' },
    { label: 'Tissue', value: resolver.tissue, field: 'tissue' },
  ]
  return (
    <>
      <PageHeading
        eyebrow="02 / Resolve"
        title="Review the resolved input"
        description="Make the assumptions visible before drawing conclusions. These fields come from the prepared fixture."
      />
      <AnalysisSteps active={1} />
      <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_280px]">
        <section aria-label="Resolved fields" className="min-w-0">
          <dl className="divide-y divide-rule border-y border-rule">
            {rows.map((row) => (
              <div
                key={row.field}
                className="grid gap-3 py-5 sm:grid-cols-[110px_minmax(0,1fr)_auto] sm:items-center"
              >
                <dt className="text-xs text-muted">{row.label}</dt>
                <dd className="text-sm leading-6">{row.value ?? 'Not reported'}</dd>
                <dd>
                  {resolver.assumptions.some((item) => item.startsWith(row.field + ':')) ? (
                    <Badge tone="assumption">Assumption</Badge>
                  ) : (
                    <Badge>Fixture value</Badge>
                  )}
                </dd>
              </div>
            ))}
          </dl>
          <div className="mt-6 flex flex-wrap justify-between gap-3">
            <Button variant="secondary" onClick={onBack}>
              <Icon name="back" />
              Back to input
            </Button>
            <Button onClick={onContinue}>
              Explore evidence
              <Icon name="arrow" />
            </Button>
          </div>
        </section>
        <aside className="border border-assumption/20 bg-assumption/5 p-5">
          <Badge tone="assumption">Review required</Badge>
          <h2 className="mt-4 text-sm font-medium">Assumptions to review</h2>
          <ul className="mt-4 space-y-5">
            {resolver.assumptions.map((item) => (
              <li key={item} className="text-sm leading-7 text-muted">
                {item}
              </li>
            ))}
          </ul>
          <p className="mt-6 border-t border-assumption/20 pt-4 text-xs leading-6 text-muted">
            Resolver values remain static when you change the evidence cutoff. This review does not
            verify the assumptions.
          </p>
        </aside>
      </div>
    </>
  )
}
