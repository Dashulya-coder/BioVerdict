/** Opens a claim in "Claims and their evidence" and brings it into view: a risk leads to its claim. */
export function showClaim(claimId: string) {
  const row = document.getElementById(`claim-${claimId}`)
  const details = row?.querySelector('details')
  if (!row || !details) return
  details.open = true
  row.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
