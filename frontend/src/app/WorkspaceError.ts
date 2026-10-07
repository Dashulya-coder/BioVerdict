/** An actionable message safe to display to the user. */
export class WorkspaceError extends Error {
  readonly recovery: 'edit' | 'reload'

  constructor(message: string, recovery: 'edit' | 'reload') {
    super(message)
    this.name = 'WorkspaceError'
    this.recovery = recovery
  }
}
