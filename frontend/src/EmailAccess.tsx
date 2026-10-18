import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'

import type { EmailLink } from './emailLink'

export function EmailAccess({
  deliveryEnabled,
  onSignedIn,
  link = null,
  csrfToken = '',
  onCompleted,
  onCancel,
}: {
  deliveryEnabled: boolean
  onSignedIn: () => Promise<void>
  link?: EmailLink | null
  csrfToken?: string
  onCompleted?: () => Promise<void>
  onCancel?: () => void
}) {
  const [mode, setMode] = useState<'login' | 'signup' | 'reset'>('login')
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const title = link
    ? link.purpose === 'reset'
      ? 'Choose a new password'
      : 'Choose your password'
    : mode === 'login'
      ? 'Sign in with email'
      : mode === 'signup'
        ? 'Create an account'
        : 'Reset your password'

  function changeMode(next: typeof mode) {
    setMode(next)
    setPassword('')
    setConfirmation('')
    setError('')
    setMessage('')
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    setError('')
    setMessage('')
    if (link && password !== confirmation) {
      setError('Passwords do not match.')
      setPassword('')
      setConfirmation('')
      return
    }
    const secret = password
    setPassword('')
    setConfirmation('')
    setBusy(true)
    const path = link
      ? '/auth/email/complete'
      : mode === 'login'
        ? '/auth/email/login'
        : `/auth/email/request/${mode}`
    const body = link
      ? { purpose: link.purpose, token: link.token, password: secret }
      : mode === 'login'
        ? { email, password: secret }
        : { email, name }
    try {
      const response = await fetch(path, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
        },
        body: JSON.stringify(body),
      })
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(
          typeof data.detail === 'string'
            ? data.detail
            : 'Unable to complete this request. Try again.',
        )
      }
      if (link) await onCompleted?.()
      else if (mode === 'login') await onSignedIn()
      else
        setMessage(
          'If this request can be completed, an email will arrive shortly. Check spam or try again later.',
        )
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'Unable to connect. Please try again.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="email-access" aria-labelledby="email-access-heading">
      <h2 id="email-access-heading">{title}</h2>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      <form onSubmit={submit} aria-label={title}>
        {!link && mode === 'signup' && (
          <label htmlFor="signup-name">
            Name
            <input
              id="signup-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoComplete="name"
              required
              maxLength={100}
              disabled={busy}
            />
          </label>
        )}
        {!link && (
          <label htmlFor="signin-email">
            Email
            <input
              id="signin-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="username"
              required
              maxLength={254}
              disabled={busy}
            />
          </label>
        )}
        {(link || mode === 'login') && (
          <label htmlFor="signin-password">
            {link ? 'New password' : 'Password'}
            <input
              id="signin-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={link ? 'new-password' : 'current-password'}
              required
              minLength={link ? 15 : 1}
              maxLength={128}
              disabled={busy}
            />
          </label>
        )}
        {link && (
          <>
            <p>
              Use 15–128 characters. Long passphrases and password managers are
              welcome.
            </p>
            <label htmlFor="confirm-password">
              Confirm password
              <input
                id="confirm-password"
                type="password"
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                autoComplete="new-password"
                required
                minLength={15}
                maxLength={128}
                disabled={busy}
              />
            </label>
          </>
        )}
        {!link && mode === 'signup' && (
          <p>
            We’ll email a verification link. You’ll choose a password after
            verifying your address.
          </p>
        )}
        <Button
          type="submit"
          disabled={busy || (!link && mode !== 'login' && !deliveryEnabled)}
        >
          {busy
            ? 'Please wait…'
            : link
              ? 'Save password'
              : mode === 'login'
                ? 'Sign in'
                : mode === 'signup'
                  ? 'Send verification link'
                  : 'Send reset link'}
        </Button>
      </form>
      <div className="email-access-actions">
        {link ? (
          <Button variant="ghost" disabled={busy} onClick={onCancel}>
            Back to sign in
          </Button>
        ) : (
          <>
            {mode !== 'login' && (
              <Button
                variant="ghost"
                disabled={busy}
                onClick={() => changeMode('login')}
              >
                Back to sign in
              </Button>
            )}
            {mode !== 'signup' && (
              <Button
                variant="ghost"
                disabled={busy || !deliveryEnabled}
                onClick={() => changeMode('signup')}
              >
                Create account
              </Button>
            )}
            {mode !== 'reset' && (
              <Button
                variant="ghost"
                disabled={busy || !deliveryEnabled}
                onClick={() => changeMode('reset')}
              >
                Forgot password?
              </Button>
            )}
          </>
        )}
      </div>
      {!deliveryEnabled && !link && (
        <p className="auth-note">
          Account creation and password recovery need email delivery configured
          by the installation owner. Existing password sign-in still works.
        </p>
      )}
    </section>
  )
}
