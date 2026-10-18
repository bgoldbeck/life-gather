import { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { CandidateComparison } from './CandidateComparison'

type Decision = {
  id: string
  recorded_at: number
  superseded_at: number | null
  quantity?: number
  unit?: number
  name?: string
  quote?: string
  source_id?: string
}
type Target = { id: string; name: string; recorded_at: number }

export function AssetActions({
  assetId,
  head,
  decisions,
  csrfToken,
  onChanged,
  onOpen,
  assetName = 'Current item',
}: {
  assetId: string
  head: string
  decisions: Decision[]
  csrfToken: string
  onChanged: () => Promise<void>
  onOpen?: (id: string) => Promise<void>
  assetName?: string
}) {
  const [operation, setOperation] = useState('ownership')
  const [status, setStatus] = useState('')
  const [note, setNote] = useState('')
  const [eventDate, setEventDate] = useState('')
  const [today] = useState(() => new Date().toISOString().slice(0, 10))
  const [decision, setDecision] = useState('')
  const [target, setTarget] = useState('')
  const [query, setQuery] = useState('')
  const [targets, setTargets] = useState<Target[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [retry, setRetry] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef<Record<string, unknown> | null>(null)
  async function candidates(more = false) {
    setBusy(true)
    setError('')
    try {
      const response = await fetch(
        `/api/assets?include_history=true&query=${encodeURIComponent(query)}${more ? '&cursor=' + cursor : ''}`,
        { credentials: 'same-origin', cache: 'no-store' },
      )
      if (!response.ok) throw new Error()
      const page = await response.json()
      if (!more) setTarget('')
      setTargets((current) =>
        more
          ? [
              ...current,
              ...page.items.filter((row: Target) => row.id !== assetId),
            ]
          : page.items.filter((row: Target) => row.id !== assetId),
      )
      setCursor(page.next_cursor)
    } catch {
      setError('Unable to load target items. Please try again.')
    } finally {
      setBusy(false)
    }
  }
  async function save() {
    if (busy) return
    setBusy(true)
    setError('')
    const body = pending.current ?? {
      asset_id: assetId,
      request_id: crypto.randomUUID(),
      expected_action_id: head,
      operation,
      note,
      status: operation === 'ownership' ? status : null,
      event_date: operation === 'ownership' ? eventDate || null : null,
      decision_id: operation === 'ownership' ? null : decision,
      target_asset_id:
        operation === 'reassociate' && target !== 'new' ? target : null,
    }
    pending.current = body
    let saved = false
    try {
      const response = await fetch('/api/assets/actions', {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify(body),
      })
      if (!response.ok) {
        if (response.status < 500) {
          pending.current = null
          setRetry(false)
          setError(
            'Unable to save this correction. Reload the item to check its latest decision, and review the date and target.',
          )
          return
        }
        throw new Error()
      }
      await response.json()
      pending.current = null
      setRetry(false)
      saved = true
    } catch {
      setRetry(true)
      setError(
        'Connection lost. Retry safely checks this same correction without adding it twice.',
      )
    } finally {
      setBusy(false)
    }
    if (saved) {
      try {
        await onChanged()
      } catch {
        setError('Correction saved. Reload the item to see its latest history.')
      }
    }
  }
  const frozen = busy || retry
  const selectedDecision = decisions.find((item) => item.id === decision)
  const multipleUnits = (selectedDecision?.quantity ?? 1) > 1
  return (
    <section aria-label="Correct this asset" className="asset-correction">
      <h3>Correct this asset</h3>
      <p>
        Record your explanation. Earlier sources and decisions remain in
        history. These are your statements, not independent verification.
      </p>
      <label>
        Change to make
        <select
          value={operation}
          disabled={frozen}
          onChange={(e) => {
            setOperation(e.target.value)
            setDecision('')
            setTarget('')
          }}
        >
          <option value="ownership">Update ownership</option>
          <option value="undo">Undo a confirmation or association</option>
          <option value="reassociate">Move evidence to a different item</option>
        </select>
      </label>
      {operation === 'ownership' ? (
        <>
          <label>
            Ownership statement
            <select
              value={status}
              disabled={frozen}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="">Choose a statement</option>
              <option value="owned">I own this item</option>
              <option value="sold">I sold this item</option>
              <option value="returned">I returned this item</option>
              <option value="no_longer_owned">I no longer own this item</option>
            </select>
          </label>
          <label>
            Event date, if known
            <input
              type="date"
              value={eventDate}
              max={today}
              disabled={frozen}
              onChange={(e) => setEventDate(e.target.value)}
            />
          </label>
        </>
      ) : (
        <label>
          Current decision
          <select
            value={decision}
            disabled={frozen}
            onChange={(e) => {
              setDecision(e.target.value)
              setTarget('')
            }}
          >
            <option value="">Choose a decision</option>
            {decisions
              .filter(
                (d) =>
                  d.superseded_at === null &&
                  (operation === 'reassociate' || (d.quantity ?? 1) === 1),
              )
              .map((d) => (
                <option key={d.id} value={d.id}>
                  Recorded {new Date(d.recorded_at / 1000).toLocaleString()}
                  {` · ${d.id.slice(0, 8)}${d.name ? ' · ' + d.name : ''}`}
                  {(d.quantity ?? 1) > 1
                    ? ` · this item is unit ${(d.unit ?? 0) + 1} of ${d.quantity}`
                    : ''}
                </option>
              ))}
          </select>
        </label>
      )}
      {operation !== 'ownership' && selectedDecision?.quote && (
        <section aria-label="Selected correction evidence">
          <p>Exact source passage for the selected decision:</p>
          <blockquote>{selectedDecision.quote}</blockquote>
          {onOpen && selectedDecision.source_id && (
            <Button
              variant="outline"
              disabled={frozen}
              onClick={() => void onOpen(selectedDecision.source_id!)}
            >
              Open selected decision source
            </Button>
          )}
        </section>
      )}
      {operation === 'reassociate' && (
        <>
          <p>
            Choose the physical item explicitly. Creating a different item does
            not merge records. For a multi-unit receipt, only this item's unit
            moves; the other units keep their existing records. An existing
            target is required for multi-unit corrections.
          </p>
          <label>
            Find an existing item
            <input
              value={query}
              maxLength={200}
              disabled={frozen}
              onChange={(e) => {
                setQuery(e.target.value)
                setTarget('')
                setTargets([])
                setCursor(null)
              }}
            />
          </label>
          <Button
            variant="outline"
            disabled={frozen}
            onClick={() => void candidates()}
          >
            Find target items
          </Button>
          {cursor && (
            <Button
              variant="outline"
              disabled={frozen}
              onClick={() => void candidates(true)}
            >
              More target items
            </Button>
          )}
          {onOpen && targets.length > 0 && (
            <CandidateComparison
              key={`${assetId}:${targets.map((item) => item.id).join(',')}`}
              candidates={[{ id: assetId, name: assetName }, ...targets]}
              onOpen={onOpen}
              disabled={frozen}
              label="Compare before moving evidence"
            />
          )}
          <label>
            Evidence belongs to
            <select
              value={target}
              disabled={frozen}
              onChange={(e) => setTarget(e.target.value)}
            >
              <option value="">Choose an item</option>
              <option value="new" disabled={multipleUnits}>
                A different physical item — create a record
              </option>
              {targets.map((t) => (
                <option value={t.id} key={t.id}>
                  {t.name} · recorded{' '}
                  {new Date(t.recorded_at / 1000).toLocaleString()} ·{' '}
                  {t.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
        </>
      )}
      <label>
        Why are you changing it?
        <textarea
          value={note}
          maxLength={2000}
          rows={3}
          disabled={frozen}
          onChange={(e) => setNote(e.target.value)}
        />
      </label>
      {error && <p role="alert">{error}</p>}
      <div className="note-actions">
        <Button
          disabled={
            busy ||
            (!retry &&
              (!note.trim() ||
                (operation === 'ownership' ? !status : !decision) ||
                (operation === 'reassociate' &&
                  (!target || (multipleUnits && target === 'new')))))
          }
          onClick={() => void save()}
        >
          {busy
            ? 'Saving correction…'
            : retry
              ? 'Retry same correction'
              : 'Save correction'}
        </Button>
        <Button
          variant="outline"
          disabled={frozen}
          onClick={() => void onChanged()}
        >
          Reload item
        </Button>
      </div>
    </section>
  )
}
