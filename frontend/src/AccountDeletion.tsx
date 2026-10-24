import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { PasswordInput } from './PasswordInput'

export function AccountDeletion({
  email,
  passwordEnabled,
  csrfToken,
  refreshSession,
}: {
  email: string
  passwordEnabled: boolean
  csrfToken: string
  refreshSession?: () => Promise<void>
}) {
  const [typed, setTyped] = useState('')
  const [password, setPassword] = useState('')
  const [understood, setUnderstood] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const matches =
    typed.trim().toLowerCase() === email.trim().toLowerCase() && email !== ''
  const ready =
    matches && understood && (!passwordEnabled || password !== '') && !busy

  async function remove(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!ready) return
    setBusy(true)
    setError('')
    try {
      const response = await fetch('/api/account/delete', {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify(
          passwordEnabled ? { email: typed, password } : { email: typed },
        ),
      })
      if (response.ok || response.status === 401) {
        // Deleted (or already signed out): return to the sign-in page.
        await refreshSession?.()
        return
      }
      let detail = ''
      try {
        const body: unknown = await response.json()
        if (
          typeof body === 'object' &&
          body !== null &&
          'detail' in body &&
          typeof body.detail === 'string'
        )
          detail = body.detail
      } catch {
        // Fall back to the generic message below.
      }
      throw new Error(detail || 'Unable to delete your account. Try again.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to connect.')
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section
      className="password-settings account-deletion"
      aria-labelledby="account-deletion-heading"
    >
      <h2 id="account-deletion-heading">Delete account</h2>
      <p>
        Permanently deletes this account: every asset, memory, purchase,
        document, photo, conversation, scan and saved sign-in (Gmail, AI
        providers, password). Other accounts on this installation are not
        affected. This cannot be undone, so download your personal archive first
        if you may want your records back.
      </p>
      <p>
        Installation backups made before the deletion may still hold a copy
        until they expire.
      </p>
      <form onSubmit={(event) => void remove(event)}>
        <label>
          Type your account email ({email}) to confirm
          <input
            type="email"
            autoComplete="off"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
          />
        </label>
        {passwordEnabled && (
          <label>
            Current password
            <PasswordInput
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
        )}
        <label>
          <input
            type="checkbox"
            checked={understood}
            onChange={(event) => setUnderstood(event.target.checked)}
          />
          I understand my records and files will be permanently deleted
        </label>
        <div className="action-row">
          <Button type="submit" variant="destructive" disabled={!ready}>
            {busy ? 'Deleting…' : 'Delete account permanently'}
          </Button>
        </div>
      </form>
      {error && <p role="alert">{error}</p>}
    </section>
  )
}
