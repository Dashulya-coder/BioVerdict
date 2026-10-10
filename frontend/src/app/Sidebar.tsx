import { Icon } from '../ui/Icon'
import { apiMode } from './copy'
import type { Screen } from './models'

const analysisLinks = [
  { screen: 'new', label: 'New analysis', icon: 'plus' },
  { screen: 'evidence', label: 'Evidence', icon: 'document' },
  { screen: 'sources', label: 'Sources', icon: 'link' },
] as const
// Comparing runs and adding evidence need the API.
const resultLinks = [
  { screen: 'report', label: 'Report', icon: 'report' },
  { screen: 'compare', label: 'Compare', icon: 'compare' },
  { screen: 'trace', label: 'Trace', icon: 'trace' },
] as const
const groups = apiMode
  ? ([
      { title: 'Analysis', links: analysisLinks },
      { title: 'Results', links: resultLinks },
    ] as const)
  : ([{ title: 'Analysis', links: analysisLinks }] as const)

export function Sidebar({ screen }: { screen: Screen }) {
  const current = screen === 'resolved' ? 'new' : screen
  return (
    <aside className="border-b border-rule bg-sidebar lg:fixed lg:inset-y-0 lg:left-0 lg:flex lg:w-60 lg:flex-col lg:border-r lg:border-b-0">
      <a
        href="#new"
        className="flex min-h-16 items-center px-6 py-4"
        aria-label="BioVerdict, new analysis"
      >
        <span>
          <span className="block font-editorial text-xl leading-6 font-medium">BioVerdict</span>
          <span className="hidden text-xs text-muted lg:block">Research workspace</span>
        </span>
      </a>
      <nav
        aria-label="Main navigation"
        className="flex gap-1 overflow-x-auto px-3 pb-3 lg:mt-4 lg:flex-col lg:gap-0 lg:overflow-visible lg:pb-0"
      >
        {groups.map((group) => (
          <div key={group.title} className="flex gap-1 lg:mb-5 lg:flex-col">
            <p className="hidden px-3 pb-2 text-xs text-muted lg:block">{group.title}</p>
            {group.links.map((item) => (
              <a
                key={item.screen}
                href={`#${item.screen}`}
                aria-current={current === item.screen ? 'page' : undefined}
                className={`flex min-h-11 items-center gap-3 rounded-md px-3 py-2.5 text-sm whitespace-nowrap transition-colors ${current === item.screen ? 'bg-selected font-medium text-ink shadow-[inset_2px_0_0_var(--color-accent)]' : 'text-muted hover:bg-surface hover:text-ink'}`}
              >
                <Icon name={item.icon} className={''} />
                {item.label}
              </a>
            ))}
          </div>
        ))}
      </nav>
      <p className="mt-auto hidden border-t border-rule px-5 py-5 text-xs leading-5 text-muted lg:block">
        Evidence before conclusions.
        <br />
        Every source stays in view.
      </p>
    </aside>
  )
}
