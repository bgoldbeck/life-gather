import { useEffect, useState } from 'react'
import { isAIProvider } from './aiProviders'
import { ReconnectButton } from './ReconnectButton'
import type { ReconnectTarget } from './reconnect'

type Credential = {
  id: string
  kind: string
  provider: string
  label: string
  auth_state?: 'working' | 'reconnect' | null
}

export function ScanAIOptions({
  credential,
  model,
  onCredential,
  onModel,
  onReconnectKey,
}: {
  credential: string
  model: string
  onCredential: (value: string) => void
  onModel: (value: string) => void
  onReconnectKey?: (target: ReconnectTarget) => void
}) {
  const [entries, setEntries] = useState<Credential[]>([])
  const [message, setMessage] = useState('Loading AI connections…')
  const refused = entries.find(
    (item) => item.id === credential && item.auth_state === 'reconnect',
  )
  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      try {
        const options = {
          signal: controller.signal,
          cache: 'no-store' as const,
        }
        const [credentials, settings] = await Promise.all([
          fetch('/api/credentials?limit=100', options),
          fetch('/api/settings', options),
        ])
        if (!credentials.ok || !settings.ok) throw new Error('Unavailable')
        const page = (await credentials.json()) as { items: Credential[] }
        const consent = (await settings.json()) as {
          allow_external_ai: boolean
        }
        if (controller.signal.aborted) return
        setEntries(
          page.items.filter(
            (item) => item.kind === 'ai' && isAIProvider(item.provider),
          ),
        )
        setMessage(
          consent.allow_external_ai
            ? 'Selected email text is sent to this provider. Clear purchases create inferred assets; uncertain identities wait in Review. Uses your daily AI budget.'
            : 'Enable external AI access and add an AI connection in Settings before using discovery.',
        )
      } catch {
        if (!controller.signal.aborted)
          setMessage('Unable to load AI settings. Reopen this form to retry.')
      }
    }
    void load()
    return () => controller.abort()
  }, [])
  return (
    <>
      <label>
        Discovery AI connection
        <select
          required
          value={credential}
          onChange={(event) => onCredential(event.target.value)}
          className="block w-full rounded border bg-background p-2"
        >
          <option value="">Choose an AI connection</option>
          {entries.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label} ({item.provider})
              {item.auth_state === 'reconnect' ? ' · needs reconnect' : ''}
            </option>
          ))}
        </select>
      </label>
      {refused && (
        <div role="alert">
          <p>
            The provider refused this key; it may have expired or been revoked.
          </p>
          <ReconnectButton
            target={{
              kind: 'ai',
              provider: refused.provider,
              credential_id: refused.id,
            }}
            csrfToken=""
            onReconnectKey={onReconnectKey}
            variant="outline"
          />
        </div>
      )}
      <label>
        Discovery model
        <input
          required
          value={model}
          maxLength={100}
          pattern="[a-zA-Z0-9._:\-]+"
          onChange={(event) => onModel(event.target.value)}
          className="block w-full rounded border bg-background p-2"
        />
      </label>
      <p className="text-sm text-muted-foreground sm:col-span-2">{message}</p>
    </>
  )
}
