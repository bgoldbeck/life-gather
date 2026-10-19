import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { EmailAccess } from './EmailAccess'
import { readEmailLink } from './emailLink'
import { BuildInfo, type Build } from './BuildInfo'
import { useAppearance, type Theme } from './appearance'

type Account = { id: string; name: string; email: string }
type Session = {
  appearance?: Theme
  build?: Build
  test_login_enabled?: boolean
  email_delivery_enabled?: boolean
  email_password_enabled?: boolean
  configured: boolean
  user: Account | null
  csrf_token: string | null
}

export function AuthGate({
  children,
}: {
  children: (
    user: Account,
    signOut: () => void,
    busy: boolean,
    csrfToken: string,
    refreshSession: () => Promise<void>,
    passwordEnabled: boolean,
    deliveryEnabled: boolean,
    build?: Build,
    appearance?: Theme,
  ) => ReactNode
}) {
  const [link, setLink] = useState(readEmailLink)
  const [notice, setNotice] = useState(() =>
    new URLSearchParams(window.location.hash.slice(1)).has('auth') && !link
      ? 'This email link is invalid. Request a new verification or reset link.'
      : '',
  )
  useEffect(() => {
    if (new URLSearchParams(window.location.hash.slice(1)).has('auth')) {
      window.history.replaceState(
        null,
        '',
        window.location.pathname + window.location.search,
      )
    }
  }, [])
  const [session, setSession] = useState<Session | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useAppearance(session?.user ? (session.appearance ?? 'system') : 'system')
  const refresh = useCallback(async () => {
    try {
      const response = await fetch('/auth/session', {
        credentials: 'same-origin',
        cache: 'no-store',
      })
      if (!response.ok) throw new Error('Session check failed')
      const data: Session = await response.json()
      setSession(data)
      setError('')
    } catch {
      setSession(null)
      setError('Unable to connect to LifeGather. Please try again.')
    }
  }, [])

  useEffect(() => {
    const onFocus = () => void refresh()
    const initial = window.setTimeout(onFocus, 0)
    window.addEventListener('focus', onFocus)
    const timer = window.setInterval(onFocus, 60_000)
    return () => {
      window.removeEventListener('focus', onFocus)
      window.clearTimeout(initial)
      window.clearInterval(timer)
    }
  }, [refresh])

  async function signOut() {
    if (!session?.csrf_token || busy) return
    setBusy(true)
    try {
      const response = await fetch('/auth/logout', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRF-Token': session.csrf_token },
      })
      if (!response.ok && response.status !== 401)
        throw new Error('Logout failed')
      setSession({ ...session, user: null, csrf_token: null })
    } catch {
      setError('Unable to sign out. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  async function completed() {
    setLink(null)
    setNotice('Your password is saved. Sign in to continue.')
    await refresh()
  }

  async function enterTestWorkspace() {
    if (busy) return
    setBusy(true)
    try {
      const response = await fetch('/auth/test-login', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      })
      if (!response.ok) throw new Error('Test login failed')
      await refresh()
    } catch {
      setError('Unable to enter the test workspace. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  const testBanner = session?.test_login_enabled ? (
    <aside className="test-mode-banner" aria-label="Test mode">
      Test mode is enabled. Anyone who can reach this installation can enter the
      shared test workspace. Use test data only.
    </aside>
  ) : null

  if (session && link) {
    return (
      <main className="auth-page">
        {testBanner}
        <section className="auth-card">
          {link.purpose === 'link' && !session.user ? (
            <>
              <p role="alert">
                Sign in to the account that requested setup, then request a
                fresh link from Settings in this browser.
              </p>
              <Button onClick={() => setLink(null)}>Back to sign in</Button>
            </>
          ) : (
            <EmailAccess
              deliveryEnabled={!!session.email_delivery_enabled}
              onSignedIn={refresh}
              link={link}
              csrfToken={session.csrf_token || ''}
              onCompleted={completed}
              onCancel={() => setLink(null)}
            />
          )}
        </section>
      </main>
    )
  }

  if (session?.user) {
    return (
      <div className="authenticated-shell">
        {testBanner}
        {error && <p role="alert">{error}</p>}
        {children(
          session.user,
          () => void signOut(),
          busy,
          session.csrf_token || '',
          refresh,
          !!session.email_password_enabled,
          !!session.email_delivery_enabled,
          session.build,
          session.appearance,
        )}
      </div>
    )
  }

  const failedLogin = new URLSearchParams(window.location.search).has(
    'auth_error',
  )
  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="login-heading">
        {testBanner}
        <img src="/brand/lifegather-icon.png" width="56" height="56" alt="" />
        <h1 id="login-heading">Your life, a little more connected.</h1>
        <p>Sign in to your private LifeGather workspace.</p>
        {notice && <p role="status">{notice}</p>}
        {session?.test_login_enabled && !error && (
          <Button disabled={busy} onClick={() => void enterTestWorkspace()}>
            {busy ? 'Entering test workspace…' : 'Continue as test user'}
          </Button>
        )}
        {error ? (
          <>
            <p role="alert">{error}</p>
            <Button onClick={() => void refresh()}>Try again</Button>
          </>
        ) : session === null ? (
          <p role="status">Checking your session…</p>
        ) : session.configured ? (
          <>
            {failedLogin && (
              <p role="alert">Sign-in was not completed. Please try again.</p>
            )}
            <Button asChild>
              <a href="/auth/google/start">Continue with Google</a>
            </Button>
            <p className="auth-note">
              Your first sign-in creates your account. Email and bank
              connections are separate and are not enabled by signing in.
            </p>
          </>
        ) : !session.email_delivery_enabled ? (
          <p role="status">
            Google sign-in needs to be configured by the installation owner.
          </p>
        ) : null}
        {session && !error && (
          <EmailAccess
            deliveryEnabled={!!session.email_delivery_enabled}
            onSignedIn={refresh}
          />
        )}
        <BuildInfo build={session?.build} />
      </section>
    </main>
  )
}
