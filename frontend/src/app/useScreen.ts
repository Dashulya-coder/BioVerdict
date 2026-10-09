import { useSyncExternalStore } from 'react'
import type { Screen } from './models'

export function navigate(screen: Screen) {
  window.location.hash = screen
}
function subscribe(listener: () => void) {
  window.addEventListener('hashchange', listener)
  return () => {
    window.removeEventListener('hashchange', listener)
  }
}
function snapshot(): Screen {
  const value = window.location.hash.slice(1)
  return value === 'resolved' || value === 'evidence' || value === 'sources' || value === 'compare'
    ? value
    : 'new'
}
export function useScreen() {
  return useSyncExternalStore<Screen>(subscribe, snapshot, () => 'new')
}

/** The run the address names (`?run=<id>`), so that a reload or a shared link reopens it. */
export function rememberedRun(): string | null {
  return new URLSearchParams(window.location.search).get('run')
}
export function rememberRun(runId: string | null) {
  const url = new URL(window.location.href)
  if (runId) url.searchParams.set('run', runId)
  else url.searchParams.delete('run')
  if (url.href !== window.location.href) window.history.replaceState(null, '', url)
}
