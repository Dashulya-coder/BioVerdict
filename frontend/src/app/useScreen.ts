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
