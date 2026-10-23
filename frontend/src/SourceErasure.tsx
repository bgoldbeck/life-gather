import { useState } from 'react'
import { Button } from '@/components/ui/button'

type Counts = Record<string, number>
type Preview = { counts: Counts; fingerprint: string }

// Shown in this order; zero counts are left out.
const LABELS: [string, string, string][] = [
  ['memories', 'saved email or memory', 'saved emails and memories'],
  ['assets', 'asset', 'assets'],
  ['other_records', 'other record', 'other records (such as product models)'],
  ['facts', 'saved detail', 'saved details'],
  ['purchases', 'purchase', 'purchases'],
  ['suggestions', 'review suggestion', 'review suggestions'],
  ['maintenance', 'maintenance task', 'maintenance tasks'],
  ['documents', 'document and its file', 'documents and their files'],
  ['photos', 'photo and its file', 'photos and their files'],
  ['scans', 'scan and its results', 'scans and their results'],
  ['schedules', 'scan schedule', 'scan schedules'],
  [
    'connections',
    'Gmail connection and its saved sign-in',
    'Gmail connections',
  ],
]

function counted(count: number, one: string, many: string) {
  return `${count} ${count === 1 ? one : many}`
}

async function detail(response: Response, fallback: string) {
  try {
    const body: unknown = await response.json()
    if (
      typeof body === 'object' &&
      body !== null &&
      'detail' in body &&
      typeof body.detail === 'string'
    )
      return body.detail
  } catch {
    // Fall back to the generic message.
  }
  return fallback
}

export function SourceErasure({
  csrfToken,
  kind,
  id,
  name,
  disabled = false,
  onErased,
}: {
  csrfToken: string
  kind: 'mailbox' | 'scan'
  id: string
  name: string
  disabled?: boolean
  onErased?: () => void
}) {
  const [preview, setPreview] = useState<Preview | null>(null)
  const [understood, setUnderstood] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const action =
    kind === 'mailbox'
      ? 'Erase everything from this mailbox'
      : 'Erase what this scan saved'

  async function post(path: string, body: unknown) {
    return fetch('/api/erasure/' + path, {
      method: 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken,
      },
      body: JSON.stringify(body),
    })
  }

  async function load(notice = '') {
    setBusy(true)
    setError(notice)
    setUnderstood(false)
    try {
      const response = await post('preview', { kind, id })
      if (!response.ok)
        throw new Error(
          await detail(response, 'Unable to check what would be erased.'),
        )
      setPreview((await response.json()) as Preview)
    } catch (caught) {
      setPreview(null)
      setError(caught instanceof Error ? caught.message : 'Unable to connect.')
    } finally {
      setBusy(false)
    }
  }

  async function erase() {
    if (!preview || !understood || busy) return
    setBusy(true)
    setError('')
    try {
      const response = await post('erase', {
        kind,
        id,
        fingerprint: preview.fingerprint,
      })
      if (response.status === 409) {
        setBusy(false)
        await load(
          await detail(response, 'This source changed. Check the new list.'),
        )
        return
      }
      if (!response.ok)
        throw new Error(await detail(response, 'Unable to erase. Try again.'))
      setPreview(null)
      onErased?.()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to connect.')
    } finally {
      setBusy(false)
    }
  }

  if (!preview)
    return (
      <div className="source-erasure">
        <Button
          variant="outline"
          disabled={disabled || busy}
          onClick={() => void load()}
          aria-label={kind === 'mailbox' ? `${action}: ${name}` : undefined}
        >
          {busy ? 'Checking…' : action}
        </Button>
        {error && <p role="alert">{error}</p>}
      </div>
    )
  const lines = LABELS.filter(([key]) => (preview.counts[key] ?? 0) > 0).map(
    ([key, one, many]) => counted(preview.counts[key], one, many),
  )
  const kept =
    (preview.counts.kept_assets ?? 0) + (preview.counts.kept_records ?? 0)
  return (
    <section
      className="source-erasure space-y-2 rounded border p-3"
      aria-label={`Erase ${name}`}
    >
      <h3>Erase {name}?</h3>
      {lines.length ? (
        <>
          <p>This permanently erases:</p>
          <ul className="list-disc pl-5">
            {lines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </>
      ) : (
        <p>Nothing else was saved from this source.</p>
      )}
      {kept > 0 && (
        <p>
          {counted(kept, 'record stays', 'records stay')} because something you
          keep also mentions it. Only the details that came from this source are
          removed from it.
        </p>
      )}
      <p>
        It can’t be undone or restored. Chat conversations that quoted it, and
        backups made earlier, are not changed.
      </p>
      <label>
        <input
          type="checkbox"
          checked={understood}
          onChange={(event) => setUnderstood(event.target.checked)}
        />{' '}
        I understand this is permanent
      </label>
      <div className="action-row flex flex-wrap gap-2">
        <Button
          variant="destructive"
          disabled={!understood || busy}
          onClick={() => void erase()}
        >
          {busy ? 'Erasing…' : 'Erase permanently'}
        </Button>
        <Button
          variant="outline"
          disabled={busy}
          onClick={() => {
            setPreview(null)
            setError('')
          }}
        >
          Keep it
        </Button>
      </div>
      {error && <p role="alert">{error}</p>}
    </section>
  )
}
