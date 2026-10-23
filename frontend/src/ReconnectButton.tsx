import { useState } from 'react'
import { KeyRound } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { startGmailConsent, type ReconnectTarget } from './reconnect'

const names: Record<string, string> = {
  gmail: 'Gmail',
  openai: 'OpenAI',
  anthropic: 'Claude',
  google: 'Gemini',
}

/** One click to renew a refused sign-in: Google consent for Gmail, or the
 * Replace form in Settings for an AI key (a new key must be pasted there). */
export function ReconnectButton({
  target,
  csrfToken,
  onReconnectKey,
  onAuthorize = (url) => window.location.assign(url),
  variant = 'default',
}: {
  target: ReconnectTarget
  csrfToken: string
  onReconnectKey?: (target: ReconnectTarget) => void
  onAuthorize?: (url: string) => void
  variant?: 'default' | 'outline'
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const name = names[target.provider] ?? target.provider
  if (target.kind === 'ai' && !onReconnectKey) return null
  async function reconnect() {
    if (target.kind === 'ai') {
      onReconnectKey?.(target)
      return
    }
    setBusy(true)
    setError('')
    try {
      onAuthorize(await startGmailConsent(csrfToken))
    } catch {
      setError(
        'Unable to start Gmail consent. Check installation setup and try again.',
      )
      setBusy(false)
    }
  }
  return (
    <>
      <Button
        variant={variant}
        disabled={busy}
        onClick={() => void reconnect()}
        aria-label={`Reconnect ${name}`}
      >
        <KeyRound size={15} aria-hidden="true" />
        {busy ? 'Opening Google…' : `Reconnect ${name}`}
      </Button>
      {error && <p role="alert">{error}</p>}
    </>
  )
}
