import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'

type Mailbox = {
  id: string
  address: string
  connected: boolean
  needs_reconnect?: boolean
  revision: number
}
type Page = {
  items: Mailbox[]
  oauth_configured: boolean
  vault_configured: boolean
}

export function MailboxesPanel({
  csrfToken,
  onAuthorize = (url) => window.location.assign(url),
  onChanged,
}: {
  csrfToken: string
  onAuthorize?: (url: string) => void
  onChanged?: () => void
}) {
  const [page, setPage] = useState<Page | null>(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const alive = useRef(true)
  const request = useCallback(
    async (path = '', body?: unknown, signal?: AbortSignal) => {
      const response = await fetch('/api/mailboxes' + path, {
        method: body === undefined ? 'GET' : 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        signal,
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      })
      if (!response.ok)
        throw new Error(
          'Unable to update mailbox connection. Reload if the session or mailbox changed.',
        )
      return response.json()
    },
    [csrfToken],
  )
  useEffect(() => {
    alive.current = true
    const controller = new AbortController()
    void request('', undefined, controller.signal)
      .then((value: Page) => {
        if (!controller.signal.aborted) setPage(value)
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError(
            'Unable to load mailbox connections. Reopen Settings to retry.',
          )
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false)
      })
    return () => {
      alive.current = false
      controller.abort()
    }
  }, [request])
  async function connect() {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const value: { url: string } = await request('/google/start', {})
      if (!alive.current) return
      const target = new URL(value.url)
      if (
        target.protocol !== 'https:' ||
        target.hostname !== 'accounts.google.com' ||
        target.username ||
        target.password
      )
        throw new Error('Invalid authorization redirect')
      onAuthorize(value.url)
    } catch {
      if (alive.current)
        setError(
          'Unable to start Gmail consent. Check installation setup and try again.',
        )
    } finally {
      if (alive.current) setBusy(false)
    }
  }
  async function disconnect(mailbox: Mailbox) {
    if (busy) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const updated: Mailbox = await request('/disconnect', {
        mailbox_id: mailbox.id,
        expected_revision: mailbox.revision,
      })
      if (!alive.current) return
      setPage((current) =>
        current
          ? {
              ...current,
              items: current.items.map((row) =>
                row.id === updated.id ? updated : row,
              ),
            }
          : current,
      )
      setNotice(
        'Local mailbox credentials removed. Saved evidence remains private and available.',
      )
      onChanged?.()
    } catch {
      if (alive.current)
        setError(
          'Unable to disconnect. Retry safely, or reopen Settings if the connection changed.',
        )
    } finally {
      if (alive.current) setBusy(false)
    }
  }
  const returned = new URLSearchParams(window.location.search).get('mailbox')
  return (
    <section className="settings-panel" aria-label="Email connections">
      <h2>Email connections</h2>
      <p>
        Connect a Gmail account separately from LifeGather sign-in. Connecting
        does not scan or send mail to AI. Read-only permission does not let
        LifeGather send or delete messages.
      </p>
      {returned === 'connected' && (
        <p role="status">
          Gmail consent returned. Check the connection status below.
        </p>
      )}
      {returned === 'failed' && (
        <p role="alert">
          Gmail connection was not completed. Check setup and try again.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {busy && !page && <p role="status">Loading email connections…</p>}
      {page && (!page.oauth_configured || !page.vault_configured) && (
        <p>
          The installation owner must configure Google OAuth, the Gmail callback
          and encrypted credential storage first.
        </p>
      )}
      <Button
        disabled={busy || !page?.oauth_configured || !page.vault_configured}
        onClick={() => void connect()}
      >
        Connect Gmail
      </Button>
      {page?.items.length === 0 && <p>No mailboxes connected.</p>}
      <ul>
        {page?.items.map((mailbox) => (
          <li key={mailbox.id}>
            <strong>{mailbox.address}</strong> ·{' '}
            <span>
              {mailbox.needs_reconnect
                ? 'Access expired or was revoked. Reconnect to scan again.'
                : mailbox.connected
                  ? 'Connected for read-only access'
                  : 'Disconnected'}
            </span>
            {mailbox.needs_reconnect && (
              <Button
                disabled={
                  busy || !page?.oauth_configured || !page.vault_configured
                }
                onClick={() => void connect()}
                aria-label={'Reconnect ' + mailbox.address}
              >
                Reconnect
              </Button>
            )}
            {mailbox.connected && (
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => void disconnect(mailbox)}
                aria-label={'Disconnect ' + mailbox.address}
              >
                Disconnect
              </Button>
            )}
          </li>
        ))}
      </ul>
      <p>
        Disconnect forgets this app’s local access credentials. It does not
        delete saved evidence or revoke other Google sign-in grants. Google
        account permissions can also be managed in{' '}
        <a
          href="https://myaccount.google.com/connections"
          target="_blank"
          rel="noreferrer"
        >
          your Google account
        </a>
        .
      </p>
    </section>
  )
}
