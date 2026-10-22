import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { ScanAIOptions } from './ScanAIOptions'
import { UndoNotice, type UndoAction } from './UndoNotice'

type Schedule = {
  id: string
  label: string
  handler_key: string
  timezone: string
  cadence: 'daily' | 'weekly'
  weekday: number
  local_time: string
  lookback_days: number
  enabled: boolean
  revision: number
  next_run: number
  last_due: number | null
  last_run_id: string | null
  last_status: string
  scope: {
    mailbox_id: string
    query: string
    max_messages: number
    credential_id?: string
    model?: string
  }
}
type Draft = {
  discovery: boolean
  credential_id: string
  model: string
  label: string
  mailbox_id: string
  timezone: string
  cadence: 'daily' | 'weekly'
  weekday: number
  local_time: string
  lookback_days: number
  query: string
  max_messages: number
}
const initial = (): Draft => ({
  discovery: false,
  credential_id: '',
  model: '',
  label: '',
  mailbox_id: '',
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
  cadence: 'daily',
  weekday: 0,
  local_time: '09:00',
  lookback_days: 7,
  query: '',
  max_messages: 20,
})
const weekdays = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
]

export function ScanSchedulesPanel({
  csrfToken,
  mailboxes,
  onRun,
}: {
  csrfToken: string
  mailboxes: { id: string; address: string }[]
  onRun: (id: string) => void
}) {
  const [items, setItems] = useState<Schedule[]>([])
  const [draft, setDraft] = useState(initial)
  const [editing, setEditing] = useState<Schedule | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [undo, setUndo] = useState<UndoAction | null>(null)
  const [retry, setRetry] = useState(false)
  const [reload, setReload] = useState(0)
  const pending = useRef<{ path: string; body: unknown } | null>(null)
  const lifecycle = useRef<AbortController | null>(null)
  const request = useCallback(
    async (path: string, init?: RequestInit): Promise<unknown> => {
      const response = await fetch('/api/scan-schedules' + path, {
        ...init,
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
      })
      if (!response.ok)
        throw new Error(
          'Unable to update schedule. Refresh to check whether it changed; check the connection, timezone and scope before retrying.',
        )
      return response.json()
    },
    [csrfToken],
  )
  useEffect(() => {
    const controller = new AbortController()
    lifecycle.current = controller
    return () => controller.abort()
  }, [request])
  const selectedMailbox = draft.mailbox_id || mailboxes[0]?.id || ''
  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    async function load() {
      try {
        const page = (await request('', { signal: controller.signal })) as {
          items: Schedule[]
        }
        if (controller.signal.aborted) return
        setItems(page.items)
        if (page.items.some((item) => item.enabled))
          timer = setTimeout(() => void load(), 30000)
      } catch {
        if (!controller.signal.aborted)
          setError(
            'Unable to refresh schedules. Use Refresh schedules to retry; scheduled work may still be running.',
          )
      }
    }
    void load()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [request, reload])
  async function save(event: FormEvent) {
    event.preventDefault()
    if (busy || !lifecycle.current) return
    const controller = lifecycle.current
    if (!pending.current) {
      const data = {
        label: draft.label,
        handler_key: draft.discovery ? 'gmail_discovery' : 'gmail_import',
        config: {
          mailbox_id: selectedMailbox,
          query: draft.query,
          max_messages: draft.max_messages,
          ...(draft.discovery
            ? { credential_id: draft.credential_id, model: draft.model }
            : {}),
        },
        timezone: draft.timezone,
        cadence: draft.cadence,
        weekday: draft.weekday,
        local_time: draft.local_time,
        lookback_days: draft.lookback_days,
        request_id: crypto.randomUUID(),
      }
      pending.current = editing
        ? {
            path: `/${editing.id}/edit`,
            body: { expected_revision: editing.revision, data },
          }
        : { path: '', body: data }
    }
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await request(pending.current.path, {
        method: 'POST',
        body: JSON.stringify(pending.current.body),
        signal: controller.signal,
      })
      if (controller.signal.aborted) return
      pending.current = null
      setRetry(false)
      setEditing(null)
      setDraft(initial())
      setNotice(
        'Schedule saved. It will run while LifeGather is running, even when you are signed out.',
      )
      setReload((value) => value + 1)
    } catch {
      if (!controller.signal.aborted) {
        setRetry(true)
        setError(
          'Save was not confirmed. Retry uses the same request; if another edit won, refresh and inspect before changing the draft.',
        )
      }
    } finally {
      if (!controller.signal.aborted) setBusy(false)
    }
  }
  async function toggle(item: Schedule) {
    if (busy || !lifecycle.current) return
    const controller = lifecycle.current
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const changed = (await request(`/${item.id}/toggle`, {
        method: 'POST',
        body: JSON.stringify({
          expected_revision: item.revision,
          enabled: !item.enabled,
        }),
        signal: controller.signal,
      })) as Schedule
      if (!controller.signal.aborted) {
        setReload((value) => value + 1)
        const message = item.enabled
          ? 'Schedule paused. Existing runs can be canceled in scan history.'
          : 'Schedule resumed with the current connection; next run is in the future.'
        setNotice(message)
        setUndo({
          message,
          label: item.enabled ? 'Undo pause' : 'Undo resume',
          run: async () => {
            await request(`/${changed.id}/toggle`, {
              method: 'POST',
              body: JSON.stringify({
                expected_revision: changed.revision,
                enabled: !changed.enabled,
              }),
            })
            setReload((value) => value + 1)
            return changed.enabled
              ? 'Resume undone. The schedule is paused again.'
              : 'Pause undone. The schedule runs again with the current connection; next run is in the future.'
          },
        })
      }
    } catch {
      if (!controller.signal.aborted) {
        setError(
          'Schedule change was not confirmed. Refresh to inspect its latest state before retrying.',
        )
        setReload((value) => value + 1)
      }
    } finally {
      if (!controller.signal.aborted) setBusy(false)
    }
  }
  function edit(item: Schedule) {
    if (busy || retry) return
    setEditing(item)
    setDraft({
      discovery: item.handler_key === 'gmail_discovery',
      credential_id: item.scope.credential_id ?? '',
      model: item.scope.model ?? '',
      label: item.label,
      mailbox_id: item.scope.mailbox_id,
      timezone: item.timezone,
      cadence: item.cadence,
      weekday: item.weekday,
      local_time: item.local_time,
      lookback_days: item.lookback_days,
      query: item.scope.query,
      max_messages: item.scope.max_messages,
    })
    setError('')
    setNotice(
      'Editing resets the next run to a future occurrence. A paused schedule remains paused.',
    )
  }
  return (
    <section
      aria-label="Scan schedules"
      className="space-y-4 rounded-xl border p-4"
    >
      <h3 className="text-lg font-semibold">Scheduled scans</h3>
      <p className="text-sm text-muted-foreground">
        Daily or weekly scans use the same private import runner. No
        email-arrival triggers. After downtime, only the latest missed
        occurrence runs. Overlaps are skipped. Five schedules per user; normal
        scan limits apply.
      </p>
      {error && <p role="alert">{error}</p>}
      {undo && undo.message === notice ? (
        <UndoNotice
          action={undo}
          disabled={busy || retry}
          onBusy={setBusy}
          onDone={(message) => {
            setUndo(null)
            setNotice(message)
          }}
        />
      ) : (
        notice && <p role="status">{notice}</p>
      )}
      <form onSubmit={(event) => void save(event)} className="space-y-3">
        <fieldset
          disabled={busy || retry}
          className="grid gap-3 sm:grid-cols-2"
        >
          <label className="sm:col-span-2">
            <input
              type="checkbox"
              checked={draft.discovery}
              onChange={(event) =>
                setDraft({ ...draft, discovery: event.target.checked })
              }
            />{' '}
            Schedule purchase discovery with AI
          </label>
          {draft.discovery && (
            <ScanAIOptions
              credential={draft.credential_id}
              model={draft.model}
              onCredential={(value) =>
                setDraft({ ...draft, credential_id: value })
              }
              onModel={(value) => setDraft({ ...draft, model: value })}
            />
          )}
          <label>
            Schedule name
            <input
              required
              maxLength={100}
              value={draft.label}
              onChange={(event) =>
                setDraft({ ...draft, label: event.target.value })
              }
              className="block w-full rounded border bg-background p-2"
            />
          </label>
          <label>
            Scheduled mailbox
            <select
              required
              value={selectedMailbox}
              onChange={(event) =>
                setDraft({ ...draft, mailbox_id: event.target.value })
              }
              className="block w-full rounded border bg-background p-2"
            >
              <option value="">Choose a mailbox</option>
              {draft.mailbox_id &&
                !mailboxes.some((item) => item.id === draft.mailbox_id) && (
                  <option value={draft.mailbox_id}>
                    Disconnected mailbox — reconnect in Settings
                  </option>
                )}
              {mailboxes.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.address}
                </option>
              ))}
            </select>
          </label>
          <label>
            Frequency
            <select
              value={draft.cadence}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  cadence: event.target.value as 'daily' | 'weekly',
                })
              }
              className="block rounded border bg-background p-2"
            >
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
            </select>
          </label>
          {draft.cadence === 'weekly' && (
            <label>
              Day of week
              <select
                value={draft.weekday}
                onChange={(event) =>
                  setDraft({ ...draft, weekday: Number(event.target.value) })
                }
                className="block rounded border bg-background p-2"
              >
                {weekdays.map((day, index) => (
                  <option key={day} value={index}>
                    {day}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            Local run time
            <input
              type="time"
              required
              value={draft.local_time}
              onChange={(event) =>
                setDraft({ ...draft, local_time: event.target.value })
              }
              className="block rounded border bg-background p-2"
            />
          </label>
          <label>
            Timezone
            <input
              required
              maxLength={100}
              placeholder="America/Los_Angeles"
              value={draft.timezone}
              onChange={(event) =>
                setDraft({ ...draft, timezone: event.target.value })
              }
              className="block w-full rounded border bg-background p-2"
            />
          </label>
          <label>
            Look back days
            <input
              type="number"
              min={1}
              max={30}
              required
              value={draft.lookback_days}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  lookback_days: Number(event.target.value),
                })
              }
              className="block rounded border bg-background p-2"
            />
          </label>
          <label>
            Scheduled Gmail search
            <input
              maxLength={200}
              value={draft.query}
              onChange={(event) =>
                setDraft({ ...draft, query: event.target.value })
              }
              className="block w-full rounded border bg-background p-2"
            />
          </label>
          <label>
            Scheduled maximum messages
            <input
              type="number"
              min={1}
              max={50}
              required
              value={draft.max_messages}
              onChange={(event) =>
                setDraft({ ...draft, max_messages: Number(event.target.value) })
              }
              className="block rounded border bg-background p-2"
            />
          </label>
        </fieldset>
        <p className="text-sm text-muted-foreground">
          Daylight-saving gaps move to the first valid minute; repeated times
          run once. Each run ends at its scheduled time and reads the preceding
          lookback window. Narrow your scope if the message cap is reached.
        </p>
        <Button
          type="submit"
          disabled={
            busy || !mailboxes.some((item) => item.id === selectedMailbox)
          }
        >
          {retry
            ? 'Retry schedule save'
            : editing
              ? 'Save schedule'
              : 'Create schedule'}
        </Button>
        {(editing || retry) && (
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={() => {
              pending.current = null
              setRetry(false)
              setEditing(null)
              setDraft(initial())
              setError('')
              setNotice(
                'Draft discarded. Refresh to inspect previously requested changes.',
              )
            }}
          >
            Discard schedule draft
          </Button>
        )}
      </form>
      <Button
        type="button"
        variant="outline"
        onClick={() => {
          setError('')
          setReload((value) => value + 1)
        }}
      >
        Refresh schedules
      </Button>
      <ul className="space-y-3">
        {items.map((item) => (
          <li key={item.id} className="space-y-2 rounded border p-3">
            <h4 className="font-semibold">{item.label}</h4>
            <p>
              {item.cadence === 'weekly'
                ? 'Every ' + weekdays[item.weekday]
                : 'Daily'}{' '}
              at {item.local_time} · {item.timezone} ·{' '}
              {item.enabled ? 'Enabled' : 'Paused'}
            </p>
            <p>
              {item.enabled
                ? 'Next run: ' + new Date(item.next_run * 1000).toLocaleString()
                : 'No future dispatch while paused'}{' '}
              · {item.last_status}
            </p>
            {item.last_status === 'blocked' && (
              <p>
                Connection or scope needs attention. Reconnect in Settings, then
                explicitly resume.
              </p>
            )}
            {item.last_status === 'skipped_overlap' && (
              <p>
                Last occurrence skipped because this connection already had an
                active scan.
              </p>
            )}
            <Button
              type="button"
              variant="outline"
              disabled={busy || retry}
              onClick={() => edit(item)}
            >
              Edit {item.label}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => void toggle(item)}
            >
              {item.enabled ? 'Pause' : 'Resume'} {item.label}
            </Button>
            {item.last_run_id && (
              <Button
                type="button"
                variant="outline"
                onClick={() => onRun(item.last_run_id!)}
              >
                View last run for {item.label}
              </Button>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
