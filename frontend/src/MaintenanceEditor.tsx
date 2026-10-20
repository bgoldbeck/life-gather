import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import {
  MaintenanceError,
  type MaintenanceRequest,
  type MaintenanceTask,
} from './maintenanceTypes'

export function MaintenanceEditor({
  task,
  entityId,
  request,
  onSaved,
  onCancel,
  onReload,
}: {
  task: MaintenanceTask | null
  entityId: string
  request: MaintenanceRequest
  onSaved: () => void
  onCancel: () => void
  onReload: () => void
}) {
  const [title, setTitle] = useState(task?.revision.title ?? '')
  const [due, setDue] = useState(task?.revision.due_on ?? '')
  const [dueKnown, setDueKnown] = useState(!!task?.revision.due_on)
  const [zone, setZone] = useState(
    task?.revision.timezone ??
      Intl.DateTimeFormat().resolvedOptions().timeZone ??
      'UTC',
  )
  const [state, setState] = useState(task?.revision.state ?? 'open')
  const [completed, setCompleted] = useState(task?.revision.completed_on ?? '')
  const [completedKnown, setCompletedKnown] = useState(
    !!task?.revision.completed_on,
  )
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [stale, setStale] = useState(false)
  const active = useRef<AbortController | null>(null)
  const pending = useRef<{ signature: string; id: string } | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    heading.current?.focus()
    return () => active.current?.abort()
  }, [])
  async function save(event: FormEvent) {
    event.preventDefault()
    if (active.current || stale) return
    const payload = {
      ...(task
        ? { task_id: task.id, state_token: task.state_token }
        : { entity_id: entityId }),
      title,
      due_on: dueKnown ? due : null,
      timezone: zone,
      state,
      completed_on: state === 'completed' && completedKnown ? completed : null,
      text,
    }
    const signature = JSON.stringify(payload)
    if (pending.current?.signature !== signature)
      pending.current = { signature, id: crypto.randomUUID() }
    const controller = new AbortController()
    active.current = controller
    setBusy(true)
    setError('')
    try {
      const result = (await request(
        task ? '/api/maintenance/revise' : '/api/maintenance',
        {
          method: 'POST',
          signal: controller.signal,
          body: JSON.stringify({ ...payload, request_id: pending.current.id }),
        },
      )) as { id?: unknown; revision_id?: unknown } | null
      if (controller.signal.aborted) return
      if (
        !result ||
        typeof result.id !== 'string' ||
        !result.id ||
        typeof result.revision_id !== 'string' ||
        !result.revision_id ||
        (task && result.id !== task.id)
      )
        throw new Error('Invalid maintenance acknowledgement')
      onSaved()
    } catch (caught) {
      if (controller.signal.aborted) return
      if (caught instanceof MaintenanceError && caught.status === 409) {
        setStale(true)
        setError(
          'This task changed. Your draft is preserved. Discard it and reload before editing again.',
        )
      } else
        setError(
          caught instanceof MaintenanceError && caught.status === 401
            ? 'Your session expired. Sign in again before saving this task.'
            : 'Unable to save this task. Check the dates, timezone and source statement, then retry.',
        )
    } finally {
      if (!controller.signal.aborted) {
        active.current = null
        setBusy(false)
      }
    }
  }
  return (
    <form
      className="maintenance-editor"
      onSubmit={(event) => void save(event)}
      aria-label="Maintenance task form"
    >
      <h3 ref={heading} tabIndex={-1}>
        {task ? 'Revise maintenance task' : 'Add maintenance task'}
      </h3>
      <p>
        These are your statements, not verified maintenance recommendations.
        Missing dates stay unknown. Every saved change retains its earlier
        statement.
      </p>
      <label>
        Task title
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          required
          maxLength={200}
          disabled={busy || stale}
        />
      </label>
      <label className="maintenance-choice">
        <input
          type="checkbox"
          checked={dueKnown}
          onChange={(event) => setDueKnown(event.target.checked)}
          disabled={busy || stale}
        />
        Due date is known
      </label>
      {dueKnown ? (
        <label>
          Due date
          <input
            type="date"
            value={due}
            onChange={(event) => setDue(event.target.value)}
            required
            disabled={busy || stale}
          />
        </label>
      ) : (
        <p>Due date: Unknown</p>
      )}
      <label>
        Date timezone
        <input
          value={zone}
          onChange={(event) => setZone(event.target.value)}
          required
          maxLength={100}
          disabled={busy || stale}
          aria-describedby="maintenance-zone-hint"
        />
      </label>
      <p id="maintenance-zone-hint">
        Use an IANA timezone, such as America/Los_Angeles. Due status uses this
        timezone’s calendar date.
      </p>
      <label>
        Task state
        <select
          value={state}
          onChange={(event) => setState(event.target.value as typeof state)}
          disabled={busy || stale}
        >
          <option value="open">Open</option>
          <option value="completed">Completed</option>
          <option value="canceled">Canceled</option>
        </select>
      </label>
      {state === 'completed' && (
        <>
          <label className="maintenance-choice">
            <input
              type="checkbox"
              checked={completedKnown}
              onChange={(event) => setCompletedKnown(event.target.checked)}
              disabled={busy || stale}
            />
            Completion date is known
          </label>
          {completedKnown ? (
            <label>
              Completion date
              <input
                type="date"
                value={completed}
                onChange={(event) => setCompleted(event.target.value)}
                required
                disabled={busy || stale}
              />
            </label>
          ) : (
            <p>Completion date: Unknown</p>
          )}
        </>
      )}
      <label>
        Source statement
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          required
          maxLength={4000}
          disabled={busy || stale}
        />
      </label>
      <p>
        Save the reason or original statement for this revision. Canceling or
        reopening a task keeps its history.
      </p>
      {error && <p role="alert">{error}</p>}
      {stale && task && (
        <Button
          type="button"
          variant="outline"
          disabled={busy}
          onClick={onReload}
        >
          Discard draft and reload task
        </Button>
      )}
      <div className="maintenance-actions">
        <Button type="submit" disabled={busy || stale}>
          {busy ? 'Saving maintenance task…' : 'Save maintenance task'}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={busy}
          onClick={onCancel}
        >
          Cancel task edit
        </Button>
      </div>
    </form>
  )
}
