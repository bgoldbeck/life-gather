import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { AccountDeletion } from './AccountDeletion'

/** Shown after sign-in until the account accepts the installation's terms. */
export function TermsGate({
  version,
  email,
  passwordEnabled,
  csrfToken,
  refreshSession,
  signOut,
  busy,
}: {
  version: string
  email: string
  passwordEnabled: boolean
  csrfToken: string
  refreshSession: () => Promise<void>
  signOut: () => void
  busy: boolean
}) {
  const [text, setText] = useState<string | null>(null)
  const [loadError, setLoadError] = useState('')
  const [agreed, setAgreed] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    fetch('/auth/terms', { credentials: 'same-origin', cache: 'no-store' })
      .then(async (response) => {
        if (!response.ok) throw new Error('unavailable')
        const data: { version: string; text: string } = await response.json()
        if (active) setText(data.text)
      })
      .catch(() => {
        if (active)
          setLoadError('The terms of use could not be loaded. Try again later.')
      })
    return () => {
      active = false
    }
  }, [version])

  async function accept() {
    if (!agreed || saving) return
    setSaving(true)
    setError('')
    try {
      const response = await fetch('/auth/terms/accept', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify({ version }),
      })
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(
          typeof data.detail === 'string'
            ? data.detail
            : 'Unable to save your acceptance. Try again.',
        )
      }
      await refreshSession()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to connect.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card terms-card" aria-labelledby="terms-heading">
        <h1 id="terms-heading">Terms of use</h1>
        <p>
          Before you continue, read and accept this installation’s terms of use
          and privacy notice (version {version}).
        </p>
        {loadError ? (
          <p role="alert">{loadError}</p>
        ) : text === null ? (
          <p role="status">Loading the terms…</p>
        ) : (
          <div
            className="terms-text"
            role="region"
            aria-label="Terms of use text"
            tabIndex={0}
          >
            {text}
          </div>
        )}
        <label className="terms-agree">
          <input
            type="checkbox"
            checked={agreed}
            disabled={text === null}
            onChange={(event) => setAgreed(event.target.checked)}
          />
          I have read and agree to the terms of use and privacy notice
        </label>
        {error && <p role="alert">{error}</p>}
        <div className="action-row">
          <Button
            disabled={!agreed || saving || text === null}
            onClick={() => void accept()}
          >
            {saving ? 'Saving…' : 'Accept and continue'}
          </Button>
          <Button variant="ghost" disabled={busy} onClick={signOut}>
            Sign out
          </Button>
        </div>
        <details className="terms-decline">
          <summary>Don’t agree? Delete this account</summary>
          <AccountDeletion
            email={email}
            passwordEnabled={passwordEnabled}
            csrfToken={csrfToken}
            refreshSession={refreshSession}
          />
        </details>
      </section>
    </main>
  )
}
