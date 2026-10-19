export type WorkspaceContext = {
  page: string
  entity_id: string | null
  version: string
  name?: string | null
}

export function contextKey(context?: WorkspaceContext | null) {
  return JSON.stringify(
    context && [context.page, context.entity_id, context.version],
  )
}
