import { Icon } from '../ui/Icon'
import { apiMode } from './copy'
import type { Screen } from './models'

const snapshotLinks = [
  { screen: 'new', label: 'New analysis', icon: 'plus' },
  { screen: 'evidence', label: 'Evidence', icon: 'document' },
  { screen: 'sources', label: 'Sources', icon: 'link' },
] as const
// Comparing runs and adding evidence need the API.
const links = apiMode
  ? ([
      ...snapshotLinks,
      { screen: 'report', label: 'Report', icon: 'check' },
      { screen: 'compare', label: 'Compare', icon: 'check' },
    ] as const)
  : snapshotLinks

export function Sidebar({ screen }: { screen: Screen }) {
  return (
    <aside className="border-b border-rule bg-sidebar lg:fixed lg:inset-y-0 lg:left-0 lg:w-56 lg:border-r lg:border-b-0">
      <a
        href="#new"
        className="flex min-h-20 items-center px-6 py-6"
        aria-label="BioVerdict, new analysis"
      >
        <span className="font-editorial text-xl font-medium">BioVerdict</span>
      </a>
      <p className="hidden px-6 font-mono text-[10px] tracking-[0.15em] text-muted uppercase lg:block">
        Research workspace
      </p>
      <nav
        aria-label="Main navigation"
        className="flex gap-1 px-3 pb-3 lg:mt-8 lg:flex-col lg:pb-0"
      >
        {links.map((item) => (
          <a
            key={item.screen}
            href={`#${item.screen}`}
            aria-current={
              screen === item.screen || (screen === 'resolved' && item.screen === 'new')
                ? 'page'
                : undefined
            }
            className={`flex min-h-11 flex-1 items-center gap-3 border-l-2 px-3 py-3 text-sm lg:flex-none ${screen === item.screen || (screen === 'resolved' && item.screen === 'new') ? 'border-accent bg-selected text-ink' : 'border-transparent text-muted hover:bg-surface hover:text-ink'}`}
          >
            <Icon name={item.icon} />
            {item.label}
          </a>
        ))}
      </nav>
      <div className="mx-6 mt-7 hidden border-t border-rule pt-5 text-sm text-muted lg:block">
        <p>Underwriting</p>
        <p className="mt-3 flex justify-between text-muted/70">
          Trace <span className="text-xs">Coming soon</span>
        </p>
      </div>
      <div className="absolute bottom-7 hidden px-6 text-xs leading-6 text-muted lg:block">
        <span className="mb-2 block h-px w-8 bg-accent/50" />
        Evidence before conclusions.
        <br />
        Every source stays in view.
      </div>
    </aside>
  )
}
