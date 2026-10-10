/** Opens a claim in "Claims and their evidence" and brings it into view: a risk leads to its claim. */
export function showClaim(claimId: string) {
  const row = document.getElementById(`claim-${claimId}`)
  const details = row?.querySelector('details')
  if (!row || !details) return
  details.open = true
  row.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

/**
 * Brings a part of the report into view. The address hash names the screen (`useScreen`), so a
 * plain `#part` link would leave the report for the input screen: the jump is made by script.
 */
export function showPart(id: string, fallback?: string) {
  const part = document.getElementById(id) ?? (fallback ? document.getElementById(fallback) : null)
  part?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
