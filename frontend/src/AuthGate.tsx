import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'

type Account = { id: string; name: string; email: string }
type Session = {
  configured: boolean
  user: Account | null
  csrf_token: string | null
}

export function AuthGate({
  children,
}: {
  children: (user: Account, signOut: () => void, busy: boolean) => ReactNode
}) {
  const [session, setSession] = useState<Session | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
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

  if (session?.user) {
    return (
      <>
        {error && <p role="alert">{error}</p>}
        {children(session.user, () => void signOut(), busy)}
      </>
    )
  }

  const failedLogin = new URLSearchParams(window.location.search).has(
    'auth_error',
  )
  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="login-heading">
        <img src="/brand/lifegather-icon.png" width="56" height="56" alt="" />
        <h1 id="login-heading">Your life, a little more connected.</h1>
        <p>Sign in to your private LifeGather workspace.</p>
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
        ) : (
          <p role="status">
            Google sign-in needs to be configured by the installation owner.
          </p>
        )}
      </section>
    </main>
  )
}
