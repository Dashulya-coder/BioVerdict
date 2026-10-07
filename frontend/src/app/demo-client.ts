import rawBundle from '../../../fixtures/bundles/divarasib.json'
import rawResolver from './fixtures/divarasib-resolver.json'
import { bundleSchema, inputSchema, resolverSchema } from './schemas'
import { WorkspaceError } from './WorkspaceError'
import type { AnalysisInput, PreparedAnalysis } from './models'

/** Reads a prepared snapshot only; it performs no underwriting or network calls. */
export function prepareDemo(input: AnalysisInput): PreparedAnalysis {
  const parsed = inputSchema.safeParse(input)
  if (!parsed.success)
    throw new WorkspaceError(
      parsed.error.issues[0]?.message ?? 'Check the analysis inputs.',
      'edit',
    )
  const bundle = bundleSchema.safeParse(rawBundle)
  const resolver = resolverSchema.safeParse(rawResolver)
  if (!bundle.success || !resolver.success)
    throw new WorkspaceError(
      'The demo data could not be loaded. Reload this page to try again.',
      'reload',
    )
  const asset = parsed.data.asset.toLowerCase()
  if (!resolver.data.known_assets.some((name) => name.toLowerCase() === asset)) {
    throw new WorkspaceError(
      'This demo supports Divarasib (GDC-6036 or RG-6330). Try one of these names.',
      'edit',
    )
  }
  return {
    input: { ...parsed.data, asset: 'Divarasib' },
    resolver: resolver.data,
    evidence: bundle.data.evidence.filter(
      (item) => (item.published_at ?? item.retrieved_at.slice(0, 10)) <= parsed.data.as_of,
    ),
  }
}
