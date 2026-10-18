import { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { CandidateComparison } from './CandidateComparison'

type Target = { id: string; name: string }

export function AssetReplacement({
  assetId,
  assetName,
  head,
  withdrawId,
  csrfToken,
  onChanged,
  onOpen,
}: {
  assetId: string
  assetName: string
  head: string
  withdrawId?: string
  csrfToken: string
  onChanged: () => Promise<void>
  onOpen: (id: string) => Promise<void>
}) {
  const [query, setQuery] = useState('')
  const [targets, setTargets] = useState<Target[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [target, setTarget] = useState('')
  const [note, setNote] = useState('')
  const [date, setDate] = useState('')
  const [today] = useState(() => new Date().toISOString().slice(0, 10))
  const [busy, setBusy] = useState(false)
  const [retry, setRetry] = useState(false)
  const [saved, setSaved] = useState(false)
  const [message, setMessage] = useState('')
  const pending = useRef<{ path: string; body: object } | null>(null)
  const frozen = busy || retry || saved
  async function find(more = false) {
    setBusy(true)
    setMessage('')
    if (!more) setTarget('')
    try {
      const response = await fetch(
        `/api/assets?include_history=true&limit=5&query=${encodeURIComponent(query)}${more ? '&cursor=' + cursor : ''}`,
        { credentials: 'same-origin', cache: 'no-store' },
      )
      if (!response.ok) throw new Error()
      const page = await response.json()
      setTargets((old) => [
        ...(more ? old : []),
        ...page.items.filter((row: Target) => row.id !== assetId),
      ])
      setCursor(page.next_cursor)
    } catch {
      setMessage('Unable to find replacement items. Try again.')
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
        'Replacement change saved. Reload the item to see its history.',
      )
    } finally {
      setBusy(false)
    }
  }
  async function save(withdraw = false) {
    if (busy) return
    const request = pending.current ?? {
      path: withdraw ? 'withdraw' : 'record',
      body: withdraw
        ? { action_id: withdrawId, request_id: crypto.randomUUID(), note }
        : {
            asset_id: assetId,
            target_asset_id: target,
            expected_action_id: head,
            request_id: crypto.randomUUID(),
            note,
            event_date: date || null,
          },
    }
    pending.current = request
    setBusy(true)
    setMessage('')
    let complete = false
    try {
      const response = await fetch(`/api/assets/replacements/${request.path}`, {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify(request.body),
      })
      if (!response.ok) {
        if (response.status < 500) {
          pending.current = null
          setRetry(false)
          setMessage(
            'Replacement change refused. Reload the item and check its latest history, date and selected item. Your explanation is unchanged.',
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
      setMessage('Connection lost. Retry the same replacement change safely.')
    } finally {
      setBusy(false)
    }
    if (complete) await reload()
  }
  const selected = targets.find((item) => item.id === target)
  return (
    <section aria-label="Record a replacement" className="asset-correction">
      <h3>Record a replacement</h3>
      <p>
        Choose a distinct existing item that replaced {assetName}. Both records,
        receipt units, purchase amounts and ownership statements remain
        separate. This records your sourced statement; it does not verify the
        event or infer a sale.
      </p>
      <label>
        Find replacement item
        <input
          value={query}
          maxLength={200}
          disabled={frozen}
          onChange={(e) => {
            setQuery(e.target.value)
            setTargets([])
            setTarget('')
            setCursor(null)
          }}
        />
      </label>
      <Button variant="outline" disabled={frozen} onClick={() => void find()}>
        Find replacements
      </Button>
      {cursor && (
        <Button
          variant="outline"
          disabled={frozen}
          onClick={() => void find(true)}
        >
          More replacements
        </Button>
      )}
      {targets.length > 0 && (
        <CandidateComparison
          key={targets.map((item) => item.id).join(',')}
          candidates={[{ id: assetId, name: assetName }, ...targets]}
          onOpen={onOpen}
          disabled={frozen}
          label="Compare replacement records"
        />
      )}
      <label>
        Item that replaced this one
        <select
          value={target}
          disabled={frozen}
          onChange={(e) => setTarget(e.target.value)}
        >
          <option value="">Choose an existing item</option>
          {targets.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name} · {item.id.slice(0, 8)}
            </option>
          ))}
        </select>
      </label>
      {selected && (
        <p>
          Record: {selected.name} ({selected.id.slice(0, 8)}) replaced{' '}
          {assetName} ({assetId.slice(0, 8)}).
        </p>
      )}
      <label>
        Replacement date, if known
        <input
          type="date"
          value={date}
          max={today}
          disabled={frozen}
          onChange={(e) => setDate(e.target.value)}
        />
      </label>
      <label>
        Replacement explanation
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
          disabled={busy || saved || (!retry && (!target || !note.trim()))}
          onClick={() => void save()}
        >
          {retry ? 'Retry same replacement change' : 'Record replacement link'}
        </Button>
        {withdrawId && !retry && (
          <Button
            variant="outline"
            disabled={frozen || !note.trim()}
            onClick={() => void save(true)}
          >
            Withdraw latest replacement link
          </Button>
        )}
        {saved && (
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => void reload()}
          >
            Reload saved replacement
          </Button>
        )}
      </div>
      {withdrawId && (
        <p>
          Withdraw this item's latest replacement statement with an explanation
          above. Earlier evidence remains; ownership and receipts are unchanged.
        </p>
      )}
    </section>
  )
}
