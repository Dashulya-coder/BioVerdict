import { useState } from 'react'
import { sourceLabels } from '../../app/constants'
import { formatDate } from '../../app/format'
import { Badge } from '../../ui/Badge'
import { Button } from '../../ui/Button'
import { Icon } from '../../ui/Icon'
import type { Evidence } from '../../app/models'

export function EvidenceInspector({ evidence }: { evidence: Evidence }) {
  const [copyStatus, setCopyStatus] = useState('')
  async function copyQuote() {
    try {
      await navigator.clipboard.writeText(evidence.excerpt)
      setCopyStatus('Quote copied.')
    } catch {
      setCopyStatus('Copy is unavailable. You can select the quotation below.')
    }
  }
  return (
    <aside
      aria-label="Evidence detail"
      className="min-w-0 self-start border border-rule bg-surface p-5 xl:sticky xl:top-6"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="mb-2 text-xs text-muted">Selected evidence</p>
          <h2 className="font-mono text-lg">{evidence.id}</h2>
        </div>
        <Badge tone={evidence.type === 'source_fact' ? 'fact' : 'assumption'}>
          {evidence.type === 'source_fact' ? 'Source fact' : 'AI inference'}
        </Badge>
      </div>
      <p className="mt-4 text-sm font-medium">{evidence.source}</p>
      <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-5 text-xs">
        {[
          ['Type', sourceLabels[evidence.source_kind]],
          ['Identifier', evidence.locator?.value ?? evidence.id],
          ['Published', formatDate(evidence.published_at)],
          ['Retrieved', formatDate(evidence.retrieved_at)],
        ].map(([label, value]) => (
          <div key={label}>
            <dt className="mb-1.5 text-muted">{label}</dt>
            <dd className="leading-6 break-words">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-6 border-t border-rule pt-5">
        <h3 className="mb-4 font-editorial text-xl font-medium">Verbatim excerpt</h3>
        <blockquote className="border-l-2 border-accent/50 bg-raised p-4 text-sm leading-7 whitespace-pre-line">
          {evidence.excerpt}
        </blockquote>
      </div>
      <div className="mt-6 flex flex-wrap items-center gap-2">
        <a
          href={evidence.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex min-h-11 items-center gap-2 rounded-sm border border-control px-3 text-xs text-accent hover:bg-raised"
        >
          Open original source
          <Icon name="external" />
        </a>
        <Button
          variant="ghost"
          onClick={() => {
            void copyQuote()
          }}
          className="px-3 text-xs"
        >
          Copy quote
        </Button>
      </div>
      <p role="status" className="mt-2 text-xs leading-6 text-muted">
        {copyStatus}
      </p>
      <p className="mt-4 border-t border-rule pt-4 font-mono text-[10px] leading-6 break-all text-muted">
        {evidence.url}
      </p>
      <p className="mt-3 text-xs leading-6 text-muted">
        A quoted source fact does not establish clinical efficacy by itself.
      </p>
    </aside>
  )
}
