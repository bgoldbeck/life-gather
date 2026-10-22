import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { aiProviderLabel, isAIProvider } from './aiProviders'

type Credential = { id: string; kind: string; provider: string; label: string }
export type DetailSuggestion = {
  line_total: string | null
  currency: string | null
  money_quote: string | null
  purchase_date: string | null
  date_quote: string | null
}
type Result = {
  provider: string
  model: string
  suggestion: DetailSuggestion
  ambiguities: { field: string; message: string }[]
  notes: string
}

// Asks the selected AI connection to read this receipt line. The server keeps
// only values printed in exact receipt passages; nothing is saved here.
export function ReceiptDetailSuggestions({
  id,
  index,
  csrfToken,
  disabled,
  onUse,
}: {
  id: string
  index: number
  csrfToken: string
  disabled: boolean
  onUse: (suggestion: DetailSuggestion) => void
}) {
  const [open, setOpen] = useState(false)
  const [credentials, setCredentials] = useState<Credential[]>([])
  const [credential, setCredential] = useState('')
  const [model, setModel] = useState('')
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<Result | null>(null)
  async function call(path: string, body?: unknown) {
    const response = await fetch('/api/' + path, {
      method: body === undefined ? 'GET' : 'POST',
      cache: 'no-store',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    if (!response.ok) {
      const detail = await response
        .json()
        .then((data) => (typeof data?.detail === 'string' ? data.detail : ''))
        .catch(() => '')
      throw new Error(detail || 'Request failed')
    }
    return response.json()
  }
  async function start() {
    setOpen(true)
    setError('')
    try {
      const [entries, settings, choice] = await Promise.all([
        call('credentials?limit=100'),
        call('settings'),
        call('chat/preferences'),
      ])
      const usable = ((entries?.items ?? []) as Credential[]).filter(
        (c) => c.kind === 'ai' && isAIProvider(c.provider),
      )
      setCredentials(usable)
      setConsent(settings?.allow_external_ai === true)
      if (usable.some((c) => c.id === choice?.credential_id)) {
        setCredential(choice.credential_id)
        setModel(choice.model ?? '')
      }
    } catch {
      setError('Unable to load AI connections. Try again.')
    }
  }
  async function suggest() {
    if (busy) return
    setBusy(true)
    setError('')
    setResult(null)
    try {
      setResult(
        await call('receipts/details/suggest', {
          receipt_id: id,
          index,
          credential_id: credential,
          model,
        }),
      )
    } catch (caught) {
      setError(
        `AI suggestions failed: ${(caught as Error).message}. Nothing was saved.`,
      )
    } finally {
      setBusy(false)
    }
  }
  if (!open)
    return (
      <Button
        variant="outline"
        disabled={disabled}
        onClick={() => void start()}
      >
        Suggest with AI…
      </Button>
    )
  const found = result?.suggestion
  const hasValue = !!(found?.line_total || found?.purchase_date)
  return (
    <section
      className="receipt-detail-suggestions"
      aria-label={`AI purchase-detail suggestions for item ${index + 1}`}
    >
      <h4>Suggest price, currency and date with AI</h4>
      <p>
        Sends only this receipt&apos;s saved text to the selected provider and
        uses one of your daily AI requests. Suggestions must quote the receipt
        exactly; anything not printed there is dropped. Nothing is saved until
        you review the draft and save it.
      </p>
      {!consent && <p>Enable external AI permission in Settings first.</p>}
      {error && <p role="alert">{error}</p>}
      <label>
        AI connection
        <select
          aria-label={`AI connection ${index + 1}`}
          value={credential}
          disabled={busy}
          onChange={(e) => {
            setCredential(e.target.value)
            setModel('')
          }}
        >
          <option value="">Choose connection</option>
          {credentials.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label} · {aiProviderLabel(c.provider)}
            </option>
          ))}
        </select>
      </label>
      <label>
        Model
        <input
          aria-label={`AI model ${index + 1}`}
          value={model}
          maxLength={100}
          disabled={busy}
          placeholder="Your provider model ID"
          onChange={(e) => setModel(e.target.value)}
        />
      </label>
      <Button
        disabled={disabled || busy || !consent || !credential || !model}
        onClick={() => void suggest()}
      >
        {busy ? 'Reading receipt…' : 'Get AI suggestions'}
      </Button>
      {result && found && (
        <div role="status">
          <p>
            Unverified suggestion from {aiProviderLabel(result.provider)} ·{' '}
            {result.model}
          </p>
          <p>
            Line total:{' '}
            {found.line_total
              ? `${found.currency ?? 'currency unknown'} ${found.line_total}`
              : 'not found'}{' '}
            · Purchase date: {found.purchase_date ?? 'not found'}
          </p>
          {found.money_quote && <blockquote>{found.money_quote}</blockquote>}
          {found.date_quote && <blockquote>{found.date_quote}</blockquote>}
          {result.ambiguities.length > 0 && (
            <>
              <p>Check before saving:</p>
              <ul aria-label={`Ambiguities for item ${index + 1}`}>
                {result.ambiguities.map((item, position) => (
                  <li key={position}>{item.message}</li>
                ))}
              </ul>
            </>
          )}
          {result.notes && <p>AI notes: {result.notes}</p>}
          {hasValue ? (
            <Button
              variant="outline"
              disabled={disabled}
              onClick={() => onUse(found)}
            >
              Copy AI suggestion into draft
            </Button>
          ) : (
            <p>No supported price or date was found; they remain unknown.</p>
          )}
        </div>
      )}
    </section>
  )
}
