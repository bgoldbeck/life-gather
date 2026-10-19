import { useEffect, useState } from 'react'

export type EmailScanScope = {
  mailbox_id: string
  from_timestamp: number
  until_timestamp: number
  query: string
  max_messages: number
}
type Mailbox = { id: string; address: string; connected: boolean }

export function ChatEmailScan({
  disabled,
  onChange,
}: {
  disabled: boolean
  onChange: (scope: EmailScanScope | null) => void
}) {
  const [mailboxes, setMailboxes] = useState<Mailbox[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [mailbox, setMailbox] = useState('')
  const [today] = useState(() => new Date().toISOString().slice(0, 10))
  const [from, setFrom] = useState(() =>
    new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10),
  )
  const [until, setUntil] = useState(today)
  const [query, setQuery] = useState('')
  const [limit, setLimit] = useState('20')
  useEffect(() => {
    const controller = new AbortController()
    void fetch('/api/mailboxes', {
      credentials: 'same-origin',
      cache: 'no-store',
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error()
        const page = await response.json()
        if (!controller.signal.aborted)
          setMailboxes(page.items.filter((row: Mailbox) => row.connected))
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError(
            'Unable to load connected mailboxes. Reopen this action to retry.',
          )
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [])
  const start = Date.parse(from + 'T00:00:00Z') / 1000
  const end = Date.parse(until + 'T00:00:00Z') / 1000 + 86400
  const count = Number(limit)
  const valid =
    !!mailbox &&
    Number.isFinite(start) &&
    Number.isFinite(end) &&
    start >= 0 &&
    end > start &&
    end - start <= 31 * 86400 &&
    end <= Date.parse(today + 'T00:00:00Z') / 1000 + 86400 &&
    Number.isInteger(count) &&
    count >= 1 &&
    count <= 50
  useEffect(() => {
    onChange(
      valid
        ? {
            mailbox_id: mailbox,
            from_timestamp: start,
            until_timestamp: end,
            query,
            max_messages: count,
          }
        : null,
    )
  }, [valid, mailbox, start, end, query, count, onChange])
  return (
    <section aria-label="Choose email scan scope" className="chat-email-scan">
      <h3>Request an email evidence scan</h3>
      <p>
        Import original email text from one connected mailbox. This action makes
        no AI request and does not create inventory items. Attachments are
        omitted. Choose up to 31 days and 50 messages.
      </p>
      <fieldset disabled={disabled || loading}>
        <label>
          Email scan mailbox
          <select
            value={mailbox}
            onChange={(event) => setMailbox(event.target.value)}
          >
            <option value="">Choose a connected mailbox</option>
            {mailboxes.map((row) => (
              <option key={row.id} value={row.id}>
                {row.address}
              </option>
            ))}
          </select>
        </label>
        <label>
          Scan from (UTC)
          <input
            type="date"
            value={from}
            onChange={(event) => setFrom(event.target.value)}
          />
        </label>
        <label>
          Scan through (UTC)
          <input
            type="date"
            value={until}
            max={today}
            onChange={(event) => setUntil(event.target.value)}
          />
        </label>
        <label>
          Email filter (optional)
          <input
            value={query}
            maxLength={200}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label>
          Maximum messages
          <input
            type="number"
            min={1}
            max={50}
            step={1}
            value={limit}
            onChange={(event) => setLimit(event.target.value)}
          />
        </label>
      </fieldset>
      <p>
        The through date includes that UTC day, up to the moment you request it.
        A queued scan continues after leaving Chat; use Scans to view progress
        or cancel.
      </p>
      {mailbox && !valid && (
        <p role="alert">
          Choose a valid past UTC range of at most 31 days and a message limit
          from 1 to 50.
        </p>
      )}
      {loading && <p role="status">Loading connected mailboxes…</p>}
      {!loading && !error && !mailboxes.length && (
        <p>Connect Gmail in Settings before requesting an email scan.</p>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  )
}
