import { useEffect, useState } from 'react'
import { ChatPanel } from './ChatPanel'
import type { WorkspaceContext } from './workspaceContext'
import type { ReconnectTarget } from './reconnect'

export function WorkspaceAssistant({
  page,
  entityId,
  revision,
  ...props
}: {
  page: string
  entityId: string | null
  revision: number
  csrfToken: string
  refreshSession?: () => Promise<void>
  initialReceiptSourceId?: string
  onOpenAsset: (id: string) => void
  onOpenMaintenance?: (id: string) => void
  onOpenGraph: (id: string) => void
  onOpenScan: (id: string) => void
  onReconnectKey?: (target: ReconnectTarget) => void
  onRecordChanged: (id: string) => void
}) {
  const [attempt, setAttempt] = useState(0)
  const [failedKey, setFailedKey] = useState('')
  const [snapshot, setSnapshot] = useState<{
    key: string
    context: WorkspaceContext
  } | null>(null)
  const key = JSON.stringify([page, entityId, revision, attempt])
  const refreshSession = props.refreshSession
  useEffect(() => {
    const controller = new AbortController()
    void fetch('/api/chat/context', {
      method: 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page, entity_id: entityId }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (response.status === 401) await refreshSession?.()
        if (!response.ok) throw new Error('Context unavailable')
        const context = (await response.json()) as WorkspaceContext
        if (!controller.signal.aborted) setSnapshot({ key, context })
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailedKey(key)
      })
    return () => controller.abort()
  }, [page, entityId, revision, key, refreshSession])
  const context = snapshot?.key === key ? snapshot.context : null
  return (
    <>
      {failedKey === key && (
        <p role="alert">
          Page context is unavailable.{' '}
          <button
            type="button"
            onClick={() => setAttempt((value) => value + 1)}
          >
            Retry page context
          </button>
        </p>
      )}
      <ChatPanel
        {...props}
        defaultMode="assistant"
        compact
        context={context}
        contextLoading={!context}
      />
    </>
  )
}
