import { useEffect, useState } from 'react'
import { isAIProvider } from './aiProviders'

type Credential = { id: string; kind: string; provider: string; label: string }

export function ScanAIOptions({
  credential,
  model,
  onCredential,
  onModel,
}: {
  credential: string
  model: string
  onCredential: (value: string) => void
  onModel: (value: string) => void
}) {
  const [entries, setEntries] = useState<Credential[]>([])
  const [message, setMessage] = useState('Loading AI connections…')
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
            </option>
          ))}
        </select>
      </label>
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
