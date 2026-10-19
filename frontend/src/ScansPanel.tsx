import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { EvidencePanel, type EvidenceSource } from './EvidencePanel'
import { ScanSchedulesPanel } from './ScanSchedulesPanel'
import { ScanAIOptions } from './ScanAIOptions'

type Mailbox = { id: string; address: string; connected: boolean }
type Run = {
  id: string
  handler_key: string
  state: string
  created_at: number
  scanned: number
  imported: number
  existing: number
  skipped: number
  truncated?: boolean
  error?: string | null
  cancel_requested?: boolean
}
type Result = Run & {
  items: {
    sequence: number
    source_id: string | null
    label: string
    state: string
    reason: string
    metadata?: {
      created?: number
      enriched?: number
      review?: number
      reused?: boolean
    }
  }[]
  next_after: number | null
}
type Evidence = EvidenceSource & { next_offset: number | null }

export function ScansPanel({
  csrfToken,
  onNavigate,
}: {
  csrfToken: string
  onNavigate?: (view: 'Review' | 'Assets') => void
}) {
  const [discovery, setDiscovery] = useState(false)
  const [credential, setCredential] = useState('')
  const [model, setModel] = useState('')
  const [mailboxes, setMailboxes] = useState<Mailbox[]>([])
  const [mailbox, setMailbox] = useState('')
  const [from, setFrom] = useState(() =>
    new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10),
  )
  const [until, setUntil] = useState(() =>
    new Date().toISOString().slice(0, 10),
  )
  const [query, setQuery] = useState('')
  const [limit, setLimit] = useState(20)
  const [runs, setRuns] = useState<Run[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [selected, setSelected] = useState('')
  const [after, setAfter] = useState(0)
  const [result, setResult] = useState<Result | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [retry, setRetry] = useState(false)
  const [reload, setReload] = useState(0)
  const [source, setSource] = useState<Evidence | null>(null)
  const [opening, setOpening] = useState(false)
  const pending = useRef<unknown>(null)
  const lifecycle = useRef<AbortController | null>(null)
  const sourceAbort = useRef<AbortController | null>(null)
  const request = useCallback(
    async (path: string, init?: RequestInit): Promise<unknown> => {
      const response = await fetch('/api' + path, {
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
          'Unable to complete this request. Check your session, connection and scan scope.',
        )
      return response.json()
    },
    [csrfToken],
  )
  const chatRequest = useCallback(
    (path: string, init?: RequestInit) => request('/chat' + path, init),
    [request],
  )
  useEffect(() => {
    const controller = new AbortController()
    lifecycle.current = controller
    void request('/mailboxes', { signal: controller.signal })
      .then((value) => {
        if (controller.signal.aborted) return
        const connected = (value as { items: Mailbox[] }).items.filter(
          (item) => item.connected,
        )
        setMailboxes(connected)
        setMailbox(connected[0]?.id ?? '')
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError('Unable to load mailboxes. Reopen Scans to retry.')
      })
    return () => {
      controller.abort()
      sourceAbort.current?.abort()
    }
  }, [request])
  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    async function load() {
      try {
        const page = (await request('/scans', {
          signal: controller.signal,
        })) as { items: Run[]; next_cursor: string | null }
        if (controller.signal.aborted) return
        setRuns(page.items)
        setCursor(page.next_cursor)
        let detail: Result | null = null
        if (selected) {
          detail = (await request(`/scans/${selected}?after=${after}`, {
            signal: controller.signal,
          })) as Result
          if (controller.signal.aborted) return
          setResult(detail)
        }
        const active =
          page.items.some((row) => ['queued', 'running'].includes(row.state)) ||
          (detail && ['queued', 'running'].includes(detail.state))
        timer = setTimeout(() => void load(), active ? 2000 : 15000)
      } catch {
        if (!controller.signal.aborted)
          setError(
            'Unable to refresh scans. Your requested work may still be running. Use Refresh scans.',
          )
      }
    }
    void load()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [request, selected, after, reload])
  async function start(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    const controller = lifecycle.current
    if (!controller) return
    setBusy(true)
    setError('')
    if (!pending.current)
      pending.current = {
        handler_key: discovery ? 'gmail_discovery' : 'gmail_import',
        request_id: crypto.randomUUID(),
        config: {
          mailbox_id: mailbox,
          from_timestamp: Date.parse(from + 'T00:00:00Z') / 1000,
          until_timestamp: Math.floor(
            Math.min(
              Date.now() / 1000,
              Date.parse(until + 'T00:00:00Z') / 1000 + 86400,
            ),
          ),
          query,
          max_messages: limit,
          ...(discovery ? { credential_id: credential, model } : {}),
        },
      }
    try {
      const run = (await request('/scans', {
        method: 'POST',
        body: JSON.stringify(pending.current),
        signal: controller.signal,
      })) as Run
      if (controller.signal.aborted) return
      pending.current = null
      setRetry(false)
      setSelected(run.id)
      setAfter(0)
      setResult(null)
      setReload((value) => value + 1)
    } catch {
      if (!controller.signal.aborted) {
        setRetry(true)
        setError(
          'The scan request was not confirmed. Retry uses the same request identity to avoid duplicate work.',
        )
      }
    } finally {
      if (!controller.signal.aborted) setBusy(false)
    }
  }
  async function cancel(id: string) {
    if (busy) return
    const controller = lifecycle.current
    if (!controller) return
    setBusy(true)
    setError('')
    try {
      await request(`/scans/${id}/cancel`, {
        method: 'POST',
        body: '{}',
        signal: controller.signal,
      })
      if (!controller.signal.aborted) setReload((value) => value + 1)
    } catch {
      if (!controller.signal.aborted)
        setError(
          'Cancellation was not confirmed. Refresh and retry if still active.',
        )
    } finally {
      if (!controller.signal.aborted) setBusy(false)
    }
  }
  async function older() {
    if (!cursor || busy) return
    const controller = lifecycle.current
    if (!controller) return
    setBusy(true)
    try {
      const page = (await request(
        '/scans?cursor=' + encodeURIComponent(cursor),
        { signal: controller.signal },
      )) as { items: Run[]; next_cursor: string | null }
      if (!controller.signal.aborted) {
        setRuns((rows) => [...rows, ...page.items])
        setCursor(page.next_cursor)
      }
    } catch {
      if (!controller.signal.aborted) setError('Unable to load older runs.')
    } finally {
      if (!controller.signal.aborted) setBusy(false)
    }
  }
  async function open(id: string, offset = 0) {
    sourceAbort.current?.abort()
    const controller = new AbortController()
    sourceAbort.current = controller
    setOpening(true)
    try {
      const next = (await chatRequest(`/sources/${id}?offset=${offset}`, {
        signal: controller.signal,
      })) as Evidence
      if (!controller.signal.aborted) setSource(next)
    } catch {
      if (!controller.signal.aborted)
        setError('Unable to open this private evidence.')
    } finally {
      if (!controller.signal.aborted) setOpening(false)
    }
  }
  return (
    <section className="space-y-5">
      <h2 className="text-xl font-semibold">Scans</h2>
      <ScanSchedulesPanel
        csrfToken={csrfToken}
        mailboxes={mailboxes}
        onRun={(id) => {
          setSelected(id)
          setAfter(0)
          setResult(null)
          setReload((value) => value + 1)
        }}
      />
      <p className="text-muted-foreground">
        Import private email text as evidence on request. Enable purchase
        discovery to use your selected AI provider and reconcile inferred
        inventory. Attachments are omitted. Find saved email evidence and
        corrections in Memories.
      </p>
      {error && <p role="alert">{error}</p>}
      <form
        onSubmit={(event) => void start(event)}
        className="space-y-3 rounded-xl border p-4"
      >
        <fieldset
          disabled={busy || retry}
          className="grid gap-3 sm:grid-cols-2"
        >
          <label className="sm:col-span-2">
            <input
              type="checkbox"
              checked={discovery}
              onChange={(event) => setDiscovery(event.target.checked)}
            />{' '}
            Discover purchases with AI
          </label>
          {discovery && (
            <ScanAIOptions
              credential={credential}
              model={model}
              onCredential={setCredential}
              onModel={setModel}
            />
          )}
          <label>
            Mailbox
            <select
              aria-label="Mailbox"
              value={mailbox}
              onChange={(event) => setMailbox(event.target.value)}
              className="block w-full rounded border bg-background p-2"
            >
              {mailboxes.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.address}
                </option>
              ))}
            </select>
          </label>
          <label>
            From date (UTC)
            <input
              type="date"
              required
              value={from}
              onChange={(event) => setFrom(event.target.value)}
              className="block rounded border bg-background p-2"
            />
          </label>
          <label>
            Through date (UTC)
            <input
              type="date"
              required
              value={until}
              onChange={(event) => setUntil(event.target.value)}
              className="block rounded border bg-background p-2"
            />
          </label>
          <label>
            Gmail search (optional)
            <input
              maxLength={200}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="block rounded border bg-background p-2"
            />
          </label>
          <label>
            Maximum messages
            <input
              type="number"
              min={1}
              max={50}
              required
              value={limit}
              onChange={(event) => setLimit(Number(event.target.value))}
              className="block rounded border bg-background p-2"
            />
          </label>
        </fieldset>
        <p className="text-sm text-muted-foreground">
          Up to 31 days and 50 messages per run; 20 runs per user per day.
          Larger mailboxes require narrower dates or searches.
        </p>
        {!mailboxes.length && <p>Connect Gmail in Settings first.</p>}
        <Button type="submit" disabled={busy || !mailbox}>
          {retry ? 'Retry scan request' : 'Start email scan'}
        </Button>
        {retry && (
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              pending.current = null
              setRetry(false)
              setError('Check run history before starting a different request.')
            }}
          >
            Discard request draft
          </Button>
        )}
      </form>
      <Button
        variant="outline"
        onClick={() => {
          setError('')
          setReload((value) => value + 1)
        }}
      >
        Refresh scans
      </Button>
      <ul className="space-y-2">
        {runs.map((run) => (
          <li key={run.id} className="rounded border p-3">
            <button
              className="text-left underline"
              onClick={() => {
                setSelected(run.id)
                setAfter(0)
                setResult(null)
              }}
            >
              {new Date(run.created_at * 1000).toLocaleString()} ·{' '}
              {run.handler_key} · {run.state}
            </button>
            <p>
              {run.scanned} checked · {run.imported} saved · {run.existing}{' '}
              already saved · {run.skipped} skipped
            </p>
            {run.truncated && (
              <p>
                Message limit reached; narrow your dates or search for the next
                scan.
              </p>
            )}
            {run.error && <p>{run.error}</p>}
            {['queued', 'running'].includes(run.state) && (
              <Button
                variant="outline"
                disabled={busy || run.cancel_requested}
                onClick={() => void cancel(run.id)}
              >
                {run.cancel_requested
                  ? 'Cancellation requested'
                  : 'Cancel scan'}
              </Button>
            )}
          </li>
        ))}
      </ul>
      {cursor && (
        <Button variant="outline" disabled={busy} onClick={() => void older()}>
          Older scans
        </Button>
      )}
      {result && (
        <section
          aria-label="Scan results"
          className="space-y-2 rounded border p-3"
        >
          <h3>Scan results · {result.state}</h3>
          {result.items.map((item) => (
            <div key={item.sequence}>
              {item.source_id ? (
                <Button
                  variant="outline"
                  disabled={opening}
                  onClick={() => void open(item.source_id!)}
                >
                  {item.label || 'Open email evidence'}
                </Button>
              ) : (
                item.label
              )}{' '}
              · {item.state} {item.reason}
              {item.metadata?.created !== undefined && (
                <p>
                  {item.metadata.created} created ·{' '}
                  {item.metadata.enriched ?? 0} enriched ·{' '}
                  {item.metadata.review ?? 0} need review
                  {item.metadata.reused &&
                    ' · previous discovery reused (no new AI call or inventory write)'}
                </p>
              )}
            </div>
          ))}
          {result.handler_key === 'gmail_discovery' && (
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => onNavigate?.('Review')}>
                Review uncertain matches
              </Button>
              <Button variant="outline" onClick={() => onNavigate?.('Assets')}>
                Inspect or correct discovered assets
              </Button>
            </div>
          )}
          {after > 0 && (
            <Button variant="outline" onClick={() => setAfter(0)}>
              First results
            </Button>
          )}
          {result.next_after && (
            <Button
              variant="outline"
              onClick={() => setAfter(result.next_after!)}
            >
              More results
            </Button>
          )}
        </section>
      )}
      {source && (
        <EvidencePanel
          key={source.id}
          source={source}
          nextOffset={source.next_offset}
          opening={opening}
          request={chatRequest}
          onOpen={open}
          onClose={() => {
            sourceAbort.current?.abort()
            setSource(null)
            setOpening(false)
          }}
        />
      )}
    </section>
  )
}
