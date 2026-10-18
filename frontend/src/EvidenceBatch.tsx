import { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { CandidateComparison } from './CandidateComparison'

type Preview = {
  preview_token: string
  asset_name: string
  target_asset_name: string
  entries: {
    decision_id: string
    name: string
    quote: string
    quote_truncated?: boolean
    source_id: string
    unit: number
    quantity: number
  }[]
}
type Target = { id: string; name: string }

export function EvidenceBatch({
  assetId,
  assetName,
  restoreId,
  csrfToken,
  onChanged,
  onOpen,
}: {
  assetId: string
  assetName: string
  restoreId?: string
  csrfToken: string
  onChanged: () => Promise<void>
  onOpen: (id: string) => Promise<void>
}) {
  const [query, setQuery] = useState('')
  const [targets, setTargets] = useState<Target[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [target, setTarget] = useState('')
  const [preview, setPreview] = useState<Preview | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [retry, setRetry] = useState(false)
  const [message, setMessage] = useState('')
  const [saved, setSaved] = useState(false)
  const pending = useRef<{ path: string; body: object } | null>(null)
  const frozen = busy || retry || saved

  async function post(path: string, body: object) {
    return fetch(`/api/assets/evidence/${path}`, {
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
  async function find(more = false) {
    setBusy(true)
    setMessage('')
    if (!more) {
      setTarget('')
      setPreview(null)
    }
    try {
      const response = await fetch(
        `/api/assets?include_history=true&query=${encodeURIComponent(query)}${more ? '&cursor=' + cursor : ''}`,
        { credentials: 'same-origin', cache: 'no-store' },
      )
      if (!response.ok) throw new Error()
      const page = await response.json()
      setTargets((old) => [
        ...(more ? old : []),
        ...page.items.filter((item: Target) => item.id !== assetId),
      ])
      setCursor(page.next_cursor)
    } catch {
      setMessage('Unable to find items. Try again.')
    } finally {
      setBusy(false)
    }
  }
  async function inspect() {
    setBusy(true)
    setMessage('')
    setPreview(null)
    try {
      const response = await post('preview', {
        asset_id: assetId,
        target_asset_id: target,
      })
      if (!response.ok) throw new Error()
      setPreview(await response.json())
    } catch {
      setMessage(
        'Unable to preview this move. It requires 1–5 current discovery associations and must keep every receipt unit distinct. Reload the item to inspect its current evidence.',
      )
    } finally {
      setBusy(false)
    }
  }
  async function reload() {
    setBusy(true)
    try {
      await onChanged()
      setMessage('Item reloaded.')
    } catch {
      setMessage(
        'Change saved. Unable to reload the item; retry the reload below.',
      )
    } finally {
      setBusy(false)
    }
  }
  async function save(restore = false) {
    if (busy) return
    const request = pending.current ?? {
      path: restore ? 'restore' : 'move',
      body: restore
        ? { action_id: restoreId, request_id: crypto.randomUUID(), note }
        : {
            asset_id: assetId,
            target_asset_id: target,
            preview_token: preview?.preview_token,
            request_id: crypto.randomUUID(),
            note,
          },
    }
    pending.current = request
    setBusy(true)
    setMessage('')
    let complete = false
    try {
      const response = await post(request.path, request.body)
      if (!response.ok) {
        if (response.status < 500) {
          pending.current = null
          setRetry(false)
          setPreview(null)
          setMessage(
            'The change was refused. Evidence or an item may have changed. Reload and preview again; no part of this request was applied.',
          )
          return
        }
        throw new Error()
      }
      await response.json()
      pending.current = null
      setRetry(false)
      setSaved(true)
      complete = true
    } catch {
      setRetry(true)
      setMessage(
        'Connection lost. Retry this same batch safely; do not start another move.',
      )
    } finally {
      setBusy(false)
    }
    if (complete) await reload()
  }
  return (
    <section
      aria-label="Move discovery evidence together"
      className="asset-correction"
    >
      <h3>Move discovery evidence together</h3>
      <p>
        Move all 1–5 current discovery associations from this item to one
        existing item. Other receipt units keep their records. Original sources
        and history remain. Notes, photos, aliases, ownership statements and
        other facts stay on their original records. This does not consolidate
        entire records.
      </p>
      <label>
        Find destination item
        <input
          value={query}
          maxLength={200}
          disabled={frozen}
          onChange={(e) => {
            setQuery(e.target.value)
            setTargets([])
            setTarget('')
            setCursor(null)
            setPreview(null)
          }}
        />
      </label>
      <Button variant="outline" disabled={frozen} onClick={() => void find()}>
        Find destinations
      </Button>
      {cursor && (
        <Button
          variant="outline"
          disabled={frozen}
          onClick={() => void find(true)}
        >
          More destinations
        </Button>
      )}
      {targets.length > 0 && (
        <CandidateComparison
          key={targets.map((item) => item.id).join(',')}
          candidates={[{ id: assetId, name: assetName }, ...targets]}
          disabled={frozen}
          onOpen={onOpen}
          label="Compare before moving a batch"
        />
      )}
      <label>
        Destination item
        <select
          value={target}
          disabled={frozen}
          onChange={(e) => {
            setTarget(e.target.value)
            setPreview(null)
          }}
        >
          <option value="">Choose an existing item</option>
          {targets.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name} · {item.id.slice(0, 8)}
            </option>
          ))}
        </select>
      </label>
      <Button
        variant="outline"
        disabled={frozen || !target}
        onClick={() => void inspect()}
      >
        Preview evidence move
      </Button>
      {preview && (
        <section aria-label="Evidence move preview">
          <p>
            {preview.entries.length} associations: {preview.asset_name} →{' '}
            {preview.target_asset_name}
          </p>
          {preview.entries.map((entry) => (
            <article key={entry.decision_id}>
              <p>
                {entry.name} · unit {entry.unit} of {entry.quantity} ·{' '}
                {entry.decision_id.slice(0, 8)}
              </p>
              <blockquote>{entry.quote}</blockquote>
              {entry.quote_truncated && (
                <p>Passage shortened. Open the source to read it in full.</p>
              )}
              <Button
                variant="outline"
                disabled={frozen}
                onClick={() => void onOpen(entry.source_id)}
              >
                Open batch source
              </Button>
            </article>
          ))}
        </section>
      )}
      <label>
        Explanation for this batch
        <textarea
          value={note}
          maxLength={2000}
          disabled={frozen}
          onChange={(e) => setNote(e.target.value)}
        />
      </label>
      {message && <p role="status">{message}</p>}
      <div className="note-actions">
        <Button
          disabled={busy || saved || (!retry && (!preview || !note.trim()))}
          onClick={() => void save()}
        >
          {retry ? 'Retry same evidence batch' : 'Move previewed evidence'}
        </Button>
        {restoreId && !retry && (
          <Button
            variant="outline"
            disabled={frozen || !note.trim()}
            onClick={() => void save(true)}
          >
            Reverse latest evidence batch
          </Button>
        )}
        {saved && (
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => void reload()}
          >
            Reload saved batch
          </Button>
        )}
      </div>
      {restoreId && (
        <p>
          Reversal restores the recorded unit mappings. Later corrections to
          either item or moved evidence can prevent reversal. Explain it above.
        </p>
      )}
    </section>
  )
}
