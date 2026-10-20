import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { EvidencePanel, type EvidenceSource } from './EvidencePanel'
import { MaintenanceEditor } from './MaintenanceEditor'
import { MaintenanceHistory } from './MaintenanceHistory'
import {
  MaintenanceError,
  maintenanceState,
  maintenanceTask,
  type MaintenanceTask,
} from './maintenanceTypes'
import './maintenance.css'

type Props = {
  entityId?: string
  csrfToken: string
  refreshSession?: () => Promise<void>
  onOpenProfile?: (id: string) => void
  onOpenGraph?: (id: string) => void
}
type Page = { items: MaintenanceTask[]; next_cursor: string | null }
type Filter = 'open' | 'completed' | 'canceled' | 'all'
function pageData(value: unknown): Page {
  const row = value as Page
  if (
    !row ||
    !Array.isArray(row.items) ||
    (row.next_cursor !== null && typeof row.next_cursor !== 'string')
  )
    throw new Error('Invalid maintenance page')
  return {
    items: row.items.map((item) => maintenanceTask(item)),
    next_cursor: row.next_cursor,
  }
}
export function MaintenancePanel(props: Props) {
  return <MaintenancePage key={props.entityId ?? 'all-records'} {...props} />
}
function MaintenancePage({
  entityId,
  csrfToken,
  refreshSession,
  onOpenProfile,
  onOpenGraph,
}: Props) {
  const request = useCallback(
    async (path: string, init?: RequestInit): Promise<unknown> => {
      const response = await fetch(
        path.startsWith('/api/') ? path : '/api/chat' + path,
        {
          ...init,
          credentials: 'same-origin',
          cache: 'no-store',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrfToken,
          },
        },
      )
      if (response.status === 401) await refreshSession?.()
      if (!response.ok) throw new MaintenanceError(response.status)
      return response.json()
    },
    [csrfToken, refreshSession],
  )
  const [page, setPage] = useState<Page | null>(null)
  const [filter, setFilter] = useState<Filter>(entityId ? 'all' : 'open')
  const [reload, setReload] = useState(0)
  const [loading, setLoading] = useState(true)
  const [paging, setPaging] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editing, setEditing] = useState<{
    task: MaintenanceTask | null
    serial: number
  } | null>(null)
  const [opening, setOpening] = useState('')
  const [history, setHistory] = useState('')
  const [source, setSource] = useState<
    (EvidenceSource & { next_offset: number | null }) | null
  >(null)
  const [sourceLoading, setSourceLoading] = useState(false)
  const generation = useRef(0)
  const editVersion = useRef(0)
  const listRead = useRef<AbortController | null>(null)
  const pageRead = useRef<AbortController | null>(null)
  const editRead = useRef<AbortController | null>(null)
  const sourceRead = useRef<AbortController | null>(null)
  const addButton = useRef<HTMLButtonElement>(null)
  const listPath = useCallback(
    (cursor = '') => {
      const params = new URLSearchParams({ state: filter, cursor })
      if (entityId) params.set('entity_id', entityId)
      return '/api/maintenance?' + params
    },
    [entityId, filter],
  )
  useEffect(() => {
    const controller = new AbortController()
    listRead.current = controller
    const version = ++generation.current
    void request(listPath(), { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted && generation.current === version)
          setPage(pageData(data))
      })
      .catch(() => {
        if (!controller.signal.aborted && generation.current === version)
          setError(
            'Unable to load maintenance tasks. Refresh the list or sign in again.',
          )
      })
      .finally(() => {
        if (!controller.signal.aborted && generation.current === version)
          setLoading(false)
      })
    return () => controller.abort()
  }, [request, listPath, reload])
  useEffect(
    () => () => {
      listRead.current?.abort()
      pageRead.current?.abort()
      editRead.current?.abort()
      sourceRead.current?.abort()
    },
    [],
  )
  function refresh(nextFilter = filter) {
    generation.current++
    listRead.current?.abort()
    pageRead.current?.abort()
    pageRead.current = null
    setPaging(false)
    setLoading(true)
    setPage(null)
    setError('')
    setFilter(nextFilter)
    setReload((value) => value + 1)
  }
  async function more() {
    if (pageRead.current || !page?.next_cursor) return
    const controller = new AbortController()
    pageRead.current = controller
    const version = generation.current
    setPaging(true)
    setError('')
    try {
      const next = pageData(
        await request(listPath(page.next_cursor), {
          signal: controller.signal,
        }),
      )
      if (!controller.signal.aborted && generation.current === version)
        setPage((current) => ({
          ...next,
          items: [
            ...new Map(
              [...(current?.items ?? []), ...next.items].map((item) => [
                item.id,
                item,
              ]),
            ).values(),
          ],
        }))
    } catch {
      if (!controller.signal.aborted && generation.current === version)
        setError(
          'Unable to load more tasks. The list may have changed; refresh it before continuing.',
        )
    } finally {
      if (!controller.signal.aborted && generation.current === version) {
        pageRead.current = null
        setPaging(false)
      }
    }
  }
  async function edit(id: string) {
    if (editRead.current) return
    const controller = new AbortController()
    editRead.current = controller
    setOpening(id)
    setError('')
    setNotice('')
    try {
      const task = maintenanceTask(
        await request(`/api/maintenance/${encodeURIComponent(id)}`, {
          signal: controller.signal,
        }),
        id,
      )
      if (!controller.signal.aborted)
        setEditing({ task, serial: ++editVersion.current })
    } catch {
      if (!controller.signal.aborted)
        setError(
          'Unable to open this task for editing. Refresh the list or sign in again.',
        )
    } finally {
      if (!controller.signal.aborted) {
        editRead.current = null
        setOpening('')
      }
    }
  }
  async function openSource(id: string, offset = 0) {
    sourceRead.current?.abort()
    const controller = new AbortController()
    sourceRead.current = controller
    setSourceLoading(true)
    try {
      const data = (await request(
        `/api/chat/sources/${encodeURIComponent(id)}?offset=${offset}`,
        { signal: controller.signal },
      )) as EvidenceSource & { next_offset: number | null }
      if (!controller.signal.aborted) {
        if (data.id !== id || typeof data.text !== 'string')
          throw new Error('Invalid source')
        setSource(data)
      }
    } catch {
      if (!controller.signal.aborted)
        setError('Unable to open the original maintenance statement.')
    } finally {
      if (!controller.signal.aborted) {
        sourceRead.current = null
        setSourceLoading(false)
      }
    }
  }
  const blocked = !!editing || !!opening
  return (
    <section
      className="maintenance-panel"
      aria-label={
        entityId ? 'Maintenance for this record' : 'Maintenance overview'
      }
    >
      {entityId ? <h2>Maintenance tasks</h2> : <h1>Maintenance</h1>}
      <p>
        Track your stated plans and completion history. Dates are optional and
        use each task’s timezone. No automatic reminders or maintenance
        intervals are inferred.
      </p>
      {!entityId && (
        <p>Add or revise tasks from the linked record’s Profiles page.</p>
      )}
      <div className="maintenance-actions">
        <label>
          Maintenance state filter
          <select
            value={filter}
            disabled={blocked}
            onChange={(event) => refresh(event.target.value as Filter)}
          >
            <option value="open">Open</option>
            <option value="completed">Completed</option>
            <option value="canceled">Canceled</option>
            <option value="all">All</option>
          </select>
        </label>
        <Button
          variant="outline"
          disabled={blocked || loading}
          onClick={() => refresh()}
        >
          Refresh maintenance tasks
        </Button>
        {entityId && (
          <Button
            ref={addButton}
            disabled={blocked || loading}
            onClick={() => {
              setNotice('')
              setEditing({ task: null, serial: ++editVersion.current })
            }}
          >
            Add maintenance task
          </Button>
        )}
      </div>
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert">{error}</p>}
      {loading && <p role="status">Loading maintenance tasks…</p>}
      {!loading && !page?.items.length && !error && (
        <p>No maintenance tasks in this view.</p>
      )}
      <ul className="maintenance-tasks">
        {page?.items.map((task) => (
          <li key={task.id}>
            <h3>{task.revision.title}</h3>
            <p>
              {task.target.name} ·{' '}
              <strong>{maintenanceState(task.due_status)}</strong>
            </p>
            <p>
              Due: {task.revision.due_on ?? 'Unknown'} ·{' '}
              {task.revision.timezone}
              {task.revision.state === 'completed'
                ? ` · Completion date: ${task.revision.completed_on ?? 'Unknown'}`
                : ''}
              .
            </p>
            <div className="maintenance-actions">
              {entityId ? (
                <Button
                  variant="outline"
                  disabled={blocked}
                  onClick={() => void edit(task.id)}
                  aria-label={`Edit ${task.revision.title}`}
                >
                  Edit task
                </Button>
              ) : (
                onOpenProfile && (
                  <Button
                    variant="outline"
                    onClick={() => onOpenProfile(task.target.id)}
                  >
                    Manage in Profiles
                  </Button>
                )
              )}
              {onOpenGraph && (
                <Button
                  variant="outline"
                  onClick={() => onOpenGraph(task.target.id)}
                >
                  View linked record
                </Button>
              )}
              <Button
                variant="outline"
                disabled={blocked}
                onClick={() => void openSource(task.revision.source_id)}
              >
                Open current statement
              </Button>
              <Button
                variant="outline"
                disabled={blocked}
                onClick={() =>
                  setHistory((current) => (current === task.id ? '' : task.id))
                }
                aria-expanded={history === task.id}
                aria-label={`History of ${task.revision.title}`}
              >
                History
              </Button>
            </div>
            {history === task.id && (
              <MaintenanceHistory
                key={`${task.id}:${task.revision.id}`}
                taskId={task.id}
                request={request}
                onOpenSource={openSource}
              />
            )}
          </li>
        ))}
      </ul>
      {paging && <p role="status">Loading more maintenance tasks…</p>}
      {page?.next_cursor && (
        <Button
          variant="outline"
          disabled={blocked || paging}
          onClick={() => void more()}
        >
          More maintenance tasks
        </Button>
      )}
      {opening && <p role="status">Opening current task revision…</p>}
      {editing && entityId && (
        <MaintenanceEditor
          key={editing.serial}
          entityId={entityId}
          task={editing.task}
          request={request}
          onCancel={() => {
            setEditing(null)
            addButton.current?.focus()
          }}
          onReload={() => {
            if (editing.task) void edit(editing.task.id)
          }}
          onSaved={() => {
            setEditing(null)
            setHistory('')
            setNotice('Maintenance task saved with its original statement.')
            refresh()
          }}
        />
      )}
      {source && (
        <EvidencePanel
          key={source.id}
          source={source}
          nextOffset={source.next_offset}
          opening={sourceLoading}
          onOpen={openSource}
          onClose={() => {
            sourceRead.current?.abort()
            setSource(null)
            setSourceLoading(false)
          }}
          request={request}
        />
      )}
    </section>
  )
}
