import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  maintenanceState,
  maintenanceRevision,
  type MaintenanceRequest,
  type MaintenanceRevision,
} from './maintenanceTypes'

type Page = { items: MaintenanceRevision[]; next_cursor: string | null }
function historyPage(value: unknown): Page {
  const row = value as Page | null
  if (
    !row ||
    !Array.isArray(row.items) ||
    (row.next_cursor !== null && typeof row.next_cursor !== 'string')
  )
    throw new Error('Invalid maintenance history')
  return {
    items: row.items.map(maintenanceRevision),
    next_cursor: row.next_cursor,
  }
}
export function MaintenanceHistory({
  taskId,
  request,
  onOpenSource,
}: {
  taskId: string
  request: MaintenanceRequest
  onOpenSource: (id: string) => Promise<void>
}) {
  const [page, setPage] = useState<Page | null>(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const active = useRef<AbortController | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    active.current = controller
    void request(`/api/maintenance/${encodeURIComponent(taskId)}/history`, {
      signal: controller.signal,
    })
      .then((result) => {
        if (!controller.signal.aborted) setPage(historyPage(result))
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError('Unable to load maintenance history.')
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          active.current = null
          setBusy(false)
        }
      })
    return () => {
      controller.abort()
      active.current?.abort()
    }
  }, [taskId, request, attempt])
  async function more() {
    if (active.current || !page?.next_cursor) return
    const controller = new AbortController()
    active.current = controller
    setBusy(true)
    setError('')
    try {
      const next = historyPage(
        await request(
          `/api/maintenance/${encodeURIComponent(taskId)}/history?cursor=${encodeURIComponent(page.next_cursor)}`,
          { signal: controller.signal },
        ),
      )
      if (!controller.signal.aborted)
        setPage((current) => ({
          ...next,
          items: [
            ...new Map(
              [...(current?.items ?? []), ...next.items].map((row) => [
                row.id,
                row,
              ]),
            ).values(),
          ],
        }))
    } catch {
      if (!controller.signal.aborted)
        setError('Unable to load maintenance history.')
    } finally {
      if (!controller.signal.aborted) {
        active.current = null
        setBusy(false)
      }
    }
  }
  return (
    <section className="maintenance-history" aria-label="Maintenance history">
      <h3>Maintenance history</h3>
      <p>
        Original statements and every saved revision. These dates describe the
        task; recording time shows when the statement was saved.
      </p>
      {busy && <p role="status">Loading maintenance history…</p>}
      {error && (
        <>
          <p role="alert">{error}</p>
          {!page && (
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => {
                setError('')
                setBusy(true)
                setAttempt((value) => value + 1)
              }}
            >
              Retry maintenance history
            </Button>
          )}
        </>
      )}
      <ol>
        {page?.items.map((row) => (
          <li key={row.id}>
            <strong>{row.title}</strong> ·{' '}
            <span>{maintenanceState(row.state)}</span>
            <p>
              Due: {row.due_on ?? 'Unknown'} · {row.timezone}. Completion date:{' '}
              {row.completed_on ?? 'Unknown'}.
            </p>
            <p>
              Recorded {new Date(row.recorded_at / 1000).toLocaleString()}
              {row.superseded_at !== null ? ' · Later revised' : ''}.
            </p>
            <p>
              {row.origin
                ? `${row.origin.method.replaceAll('_', ' ')} · ${row.origin.interface}`
                : 'Origin not recorded'}
              .
            </p>
            <Button
              variant="outline"
              onClick={() => void onOpenSource(row.source_id)}
            >
              Open revision source
            </Button>
          </li>
        ))}
      </ol>
      {page?.next_cursor && (
        <Button variant="outline" disabled={busy} onClick={() => void more()}>
          More maintenance history
        </Button>
      )}
    </section>
  )
}
