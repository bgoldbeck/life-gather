import { useState } from 'react'
import { Button } from '@/components/ui/button'

export function PasswordSettings({
  configured,
  deliveryEnabled,
  csrfToken,
  refreshSession,
}: {
  configured: boolean
  deliveryEnabled: boolean
  csrfToken: string
  refreshSession?: () => Promise<void>
}) {
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  async function requestSetup() {
    setBusy(true)
    setMessage('')
    setError('')
    try {
      const response = await fetch('/auth/email/setup', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: '{}',
      })
      if (response.status === 401) {
        await refreshSession?.()
        return
      }
      if (!response.ok)
        throw new Error('Unable to request password setup. Try again later.')
      setMessage(
        'If setup is available, a link will arrive at your account email. Open it in this browser while signed in.',
      )
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to connect.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <section
      className="password-settings"
      aria-labelledby="password-settings-heading"
    >
      <h2 id="password-settings-heading">Email and password</h2>
      {configured ? (
        <p>
          Password sign-in is enabled. Use Forgot password on the sign-in page
          to reset it.
        </p>
      ) : (
        <>
          <p>
            Add a password to this workspace by verifying your account email.
            Your Google sign-in will keep working.
          </p>
          <Button
            onClick={() => void requestSetup()}
            disabled={busy || !deliveryEnabled}
          >
            {busy ? 'Requesting…' : 'Set up password'}
          </Button>
        </>
      )}
      {!deliveryEnabled && (
        <p>
          Email delivery needs installation setup before verification or
          recovery emails can be sent.
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  )
}
