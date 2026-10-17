import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'

type Entry = {
  id: string
  kind: 'ai' | 'email' | 'bank'
  provider: string
  label: string
}
type Preferences = { allow_external_ai: boolean; vault_configured: boolean }
type Page = { items: Entry[]; next_cursor: string | null }

export function PrivateSettingsPanel({
  csrfToken,
  refreshSession,
}: {
  csrfToken: string
  refreshSession?: () => Promise<void>
}) {
  const [preferences, setPreferences] = useState<Preferences | null>(null)
  const [items, setItems] = useState<Entry[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState<Entry | null>(null)
  const [kind, setKind] = useState<Entry['kind']>('ai')
  const [provider, setProvider] = useState('')
  const [label, setLabel] = useState('')
  const [secret, setSecret] = useState('')

  const request = useCallback(
    async (path: string, init?: RequestInit) => {
      const response = await fetch(path, {
        ...init,
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
      })
      if (response.status === 401) {
        await refreshSession?.()
        throw new Error('Your session expired. Sign in again.')
      }
      if (!response.ok) {
        const message =
          response.status === 503
            ? 'Credential storage is unavailable. Ask the installation owner to check the vault key.'
            : 'Unable to save or load your settings. Please try again.'
        throw new Error(message)
      }
      return response
    },
    [csrfToken, refreshSession],
  )

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const [settingsResponse, listResponse] = await Promise.all([
          request('/api/settings', { signal }),
          request('/api/credentials', { signal }),
        ])
        const settings: Preferences = await settingsResponse.json()
        const page: Page = await listResponse.json()
        if (signal?.aborted) return
        setPreferences(settings)
        setItems(page.items)
        setCursor(page.next_cursor)
        setError('')
      } catch (caught) {
        if (!signal?.aborted)
          setError(
            caught instanceof Error
              ? caught.message
              : 'Unable to load settings.',
          )
      }
    },
    [request],
  )

  useEffect(() => {
    const controller = new AbortController()
    const initial = window.setTimeout(() => void load(controller.signal), 0)
    return () => {
      window.clearTimeout(initial)
      controller.abort()
    }
  }, [load])

  async function changeConsent(value: boolean) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await request('/api/settings', {
        method: 'PUT',
        body: JSON.stringify({ allow_external_ai: value }),
      })
      setPreferences((current) =>
        current ? { ...current, allow_external_ai: value } : current,
      )
      setNotice('Privacy preference saved.')
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    setNotice('')
    const submittedSecret = secret
    setSecret('')
    try {
      await request(
        editing ? `/api/credentials/${editing.id}` : '/api/credentials',
        {
          method: editing ? 'PUT' : 'POST',
          body: JSON.stringify(
            editing
              ? { secret: submittedSecret }
              : { kind, provider, label, secret: submittedSecret },
          ),
        },
      )
      setEditing(null)
      setProvider('')
      setLabel('')
      await load()
      setNotice('Credential saved. It has not been checked with the provider.')
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function remove(entry: Entry) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await request(`/api/credentials/${entry.id}`, { method: 'DELETE' })
      if (editing?.id === entry.id) {
        setEditing(null)
        setSecret('')
      }
      await load()
      setNotice(
        'Credential removed from LifeGather. Revoke it at the provider too if needed.',
      )
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function more() {
    if (!cursor) return
    setBusy(true)
    try {
      const response = await request(
        `/api/credentials?cursor=${encodeURIComponent(cursor)}`,
      )
      const page: Page = await response.json()
      setItems((current) => [...current, ...page.items])
      setCursor(page.next_cursor)
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="private-settings" aria-labelledby="settings-heading">
      <h1 id="settings-heading">Settings</h1>
      <p>Your privacy choices and credentials belong to your account.</p>
      {error && (
        <div role="alert">
          <p>{error}</p>
          <Button variant="outline" disabled={busy} onClick={() => void load()}>
            Reload settings
          </Button>
        </div>
      )}
      {notice && <p role="status">{notice}</p>}
      {!preferences ? (
        <p role="status">
          {error ? 'Settings unavailable.' : 'Loading settings…'}
        </p>
      ) : (
        <>
          <div className="settings-card">
            <h2>AI privacy</h2>
            <label className="consent-label">
              <input
                type="checkbox"
                checked={preferences.allow_external_ai}
                disabled={busy}
                onChange={(event) => void changeConsent(event.target.checked)}
              />
              Allow external AI processing
            </label>
            <p>
              This permits future AI features to send selected content to your
              configured provider. It does not start processing or connect any
              account.
            </p>
          </div>
          <div className="settings-card">
            <h2>Private credentials</h2>
            <p>
              Save API keys or access tokens for future integrations. Do not
              enter your email or banking password. Saving does not connect or
              validate a provider.
            </p>
            {!preferences.vault_configured && (
              <p role="status">
                The installation owner must configure a vault key before
                credentials can be saved.
              </p>
            )}
            <form onSubmit={(event) => void save(event)}>
              <fieldset disabled={busy || !preferences.vault_configured}>
                <legend>
                  {editing
                    ? `Replace credential: ${editing.label}`
                    : 'Add a credential'}
                </legend>
                {!editing && (
                  <>
                    <label>
                      Credential type
                      <select
                        value={kind}
                        onChange={(event) =>
                          setKind(event.target.value as Entry['kind'])
                        }
                      >
                        <option value="ai">AI provider</option>
                        <option value="email">Email</option>
                        <option value="bank">Bank</option>
                      </select>
                    </label>
                    <label>
                      Provider
                      <input
                        value={provider}
                        onChange={(event) => setProvider(event.target.value)}
                        required
                        maxLength={64}
                        pattern="[a-z0-9][a-z0-9_-]*"
                        placeholder="Provider identifier"
                      />
                    </label>
                    <label>
                      Label
                      <input
                        value={label}
                        onChange={(event) => setLabel(event.target.value)}
                        required
                        maxLength={100}
                        placeholder="A name you recognize"
                      />
                    </label>
                  </>
                )}
                <label>
                  API key or access token
                  <input
                    type="password"
                    value={secret}
                    onChange={(event) => setSecret(event.target.value)}
                    autoComplete="off"
                    required
                    maxLength={8192}
                  />
                </label>
                <Button type="submit">
                  {editing ? 'Replace credential' : 'Save credential'}
                </Button>
                {editing && (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setEditing(null)
                      setSecret('')
                    }}
                  >
                    Cancel replacement
                  </Button>
                )}
              </fieldset>
            </form>
            <h3>Saved credentials</h3>
            {items.length === 0 ? (
              <p>No credentials saved.</p>
            ) : (
              <ul className="credential-list">
                {items.map((entry) => (
                  <li key={entry.id}>
                    <div>
                      <strong>{entry.label}</strong>
                      <p>
                        {entry.provider} · {entry.kind} · Not validated
                      </p>
                    </div>
                    <Button
                      variant="outline"
                      disabled={busy || !preferences.vault_configured}
                      onClick={() => {
                        setEditing(entry)
                        setSecret('')
                        setNotice('')
                      }}
                      aria-label={`Replace ${entry.label}`}
                    >
                      Replace
                    </Button>
                    <Button
                      variant="outline"
                      disabled={busy}
                      onClick={() => void remove(entry)}
                      aria-label={`Remove ${entry.label}`}
                    >
                      Remove
                    </Button>
                  </li>
                ))}
              </ul>
            )}
            {cursor && (
              <Button
                disabled={busy}
                variant="outline"
                onClick={() => void more()}
              >
                Load more credentials
              </Button>
            )}
          </div>
        </>
      )}
    </section>
  )
}
