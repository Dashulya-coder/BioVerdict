import { Badge } from './ui/Badge'
import { PageHeading } from './ui/PageHeading'

export default function App() {
  return (
    <main className="mx-auto max-w-5xl px-6 py-16">
      <div className="mb-12 flex items-center justify-between border-b border-rule pb-6">
        <span className="text-lg font-medium tracking-tight">BioVerdict</span>
        <Badge>Research workspace</Badge>
      </div>
      <PageHeading
        eyebrow="Evidence first"
        title="A clearer view of the evidence."
        description="A focused workspace for biotech research, from the initial question to the original source."
      />
    </main>
  )
}
