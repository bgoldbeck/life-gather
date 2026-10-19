import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { EvidencePanel, type EvidenceSource } from './EvidencePanel'
import { ReceiptProposalCard } from './ReceiptProposalCard'
import { AssetProposalCard } from './AssetProposalCard'
import { ChatRequestError } from './chatRequest'
import './memories.css'

type Item = {
  id: string
  text: string
  kind: string
  recorded_at: number
  is_current: boolean
  is_correction: boolean
}
type Source = EvidenceSource & { next_offset: number | null }
const label: Record<string, string> = {
  notes: 'Saved note',
  photos: 'Photo transcription',
  pdfs: 'Reviewed PDF text',
  emails: 'Email evidence',
  other: 'Other evidence',
}

export function MemoriesPanel({
  csrfToken,
  refreshSession,
  onProposeReceipt,
}: {
  csrfToken: string
  onProposeReceipt?: (sourceId: string) => void
  refreshSession?: () => Promise<void>
}) {
  const [items, setItems] = useState<Item[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [kind, setKind] = useState('all')
  const [history, setHistory] = useState(false)
  const [reload, setReload] = useState(0)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [source, setSource] = useState<Source | null>(null)
  const [opening, setOpening] = useState(false)
  const [proposal, setProposal] = useState('')
  const [receipt, setReceipt] = useState('')
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [retry, setRetry] = useState(false)
  const [status, setStatus] = useState('')
  const pending = useRef<{ text: string; request_id: string } | null>(null)
  const generation = useRef(0)
  const sourceGeneration = useRef(0)
  const sourceAbort = useRef<AbortController | null>(null)
  const request = useCallback(
    async (path: string, init?: RequestInit) => {
      const response = await fetch('/api/' + path, {
        ...init,
        cache: 'no-store',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
      })
      if (response.status === 401) await refreshSession?.()
      if (!response.ok)
        throw new ChatRequestError(
          'Unable to load or save this memory. Check your session and try again.',
          response.status,
        )
      return response.json()
    },
    [csrfToken, refreshSession],
  )
  const chatRequest = useCallback(
    (path: string, init?: RequestInit) => request('chat' + path, init),
    [request],
  )
  const pagePath = useCallback(
    (next = '') =>
      `memories?query=${encodeURIComponent(search)}&kind=${kind}&include_history=${history}&cursor=${encodeURIComponent(next)}`,
    [search, kind, history],
  )
  useEffect(() => {
    const controller = new AbortController()
    const version = ++generation.current
    void request(pagePath(), { signal: controller.signal })
      .then((page) => {
        if (!controller.signal.aborted && version === generation.current) {
          setItems(page.items)
          setCursor(page.next_cursor)
        }
      })
      .catch(() => {
        if (!controller.signal.aborted && version === generation.current)
          setError('Unable to load memories. Use Refresh memories to retry.')
      })
      .finally(() => {
        if (!controller.signal.aborted && version === generation.current)
          setBusy(false)
      })
    return () => controller.abort()
  }, [request, pagePath, reload])
  useEffect(
    () => () => {
      sourceGeneration.current++
      sourceAbort.current?.abort()
    },
    [],
  )
  function refresh() {
    generation.current++
    setBusy(true)
    setError('')
    setReload((v) => v + 1)
  }
  async function more() {
    if (!cursor || busy) return
    const version = generation.current
    setBusy(true)
    setError('')
    try {
      const page = await request(pagePath(cursor))
      if (version === generation.current) {
        setItems((current) => [...current, ...page.items])
        setCursor(page.next_cursor)
      }
    } catch (caught) {
      if (version === generation.current) setError((caught as Error).message)
    } finally {
      if (version === generation.current) setBusy(false)
    }
  }
  async function open(id: string, offset = 0) {
    const version = ++sourceGeneration.current
    sourceAbort.current?.abort()
    const controller = new AbortController()
    sourceAbort.current = controller
    setOpening(true)
    setError('')
    try {
      const next = await chatRequest(`/sources/${id}?offset=${offset}`, {
        signal: controller.signal,
      })
      if (version === sourceGeneration.current) {
        setSource(next)
        // A correction changes the default current-version list too.
        if (source && source.id !== next.id) refresh()
      }
    } catch (caught) {
      if (!controller.signal.aborted && version === sourceGeneration.current)
        setError((caught as Error).message)
    } finally {
      if (version === sourceGeneration.current) setOpening(false)
    }
  }
  async function save(event: FormEvent) {
    event.preventDefault()
    if (saving || !draft.trim()) return
    setSaving(true)
    setError('')
    setStatus('')
    const body = pending.current ?? {
      text: draft,
      request_id: crypto.randomUUID(),
    }
    pending.current = body
    try {
      const saved = await request('memories', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      pending.current = null
      setRetry(false)
      setDraft('')
      setStatus(
        'Saved your exact words. No AI request or inventory change was made.',
      )
      refresh()
      await open(saved.id)
    } catch (caught) {
      if (caught instanceof ChatRequestError && caught.status < 500) {
        pending.current = null
        setRetry(false)
      } else setRetry(true)
      setError((caught as Error).message)
    } finally {
      setSaving(false)
    }
  }
  function searchNow(event: FormEvent) {
    event.preventDefault()
    setSearch(query)
    refresh()
  }
  return (
    <section className="memories-panel" aria-label="Memories library">
      <h1>Memories</h1>
      <p>
        Browse saved evidence without finding an old conversation. These are
        source statements, not independently verified facts. Unsaved chat
        messages are not included.
      </p>
      <details className="memory-capture">
        <summary>Save a memory</summary>
        <form onSubmit={(event) => void save(event)}>
          <label>
            Your original words
            <textarea
              value={draft}
              disabled={saving || retry}
              maxLength={4000}
              rows={4}
              onChange={(e) => setDraft(e.target.value)}
            />
          </label>
          <Button disabled={saving || !draft.trim()}>
            {saving ? 'Saving…' : retry ? 'Retry same memory' : 'Save memory'}
          </Button>
          <p>
            Saving preserves your text. It creates no inferred facts or
            inventory items and uses no external AI.
          </p>
        </form>
      </details>
      <form onSubmit={searchNow} className="memory-search">
        <label>
          Search saved evidence
          <input
            value={query}
            maxLength={200}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <Button>Search memories</Button>
        <label>
          Source type
          <select
            value={kind}
            onChange={(e) => {
              setKind(e.target.value)
              refresh()
            }}
          >
            <option value="all">All evidence</option>
            <option value="notes">Saved notes</option>
            <option value="photos">Photo transcriptions</option>
            <option value="pdfs">Reviewed PDF text</option>
            <option value="emails">Email evidence</option>
            <option value="other">Other evidence</option>
          </select>
        </label>
        <label className="memory-history">
          <input
            type="checkbox"
            checked={history}
            onChange={(e) => {
              setHistory(e.target.checked)
              refresh()
            }}
          />
          Include earlier versions
        </label>
      </form>
      <p>
        {history
          ? 'Includes preserved earlier statements and corrections.'
          : 'Showing the latest saved version of each note. This does not establish current ownership.'}{' '}
        Search matches every word, up to 12 words.
      </p>
      <Button variant="outline" disabled={busy} onClick={refresh}>
        Refresh memories
      </Button>
      {busy && <p role="status">Loading memories…</p>}
      {error && <p role="alert">{error}</p>}
      {status && <p role="status">{status}</p>}
      {!busy && !items.length && !error && (
        <p>
          No saved evidence matches this view. Save a note or review text from a
          photo or PDF.
        </p>
      )}
      <ul className="memory-list">
        {items.map((item) => (
          <li key={item.id}>
            <div>
              <span className="memory-kind">
                {label[item.kind] ?? 'Evidence'}
                {item.is_correction ? ' · correction' : ''}
                {!item.is_current ? ' · earlier version' : ''}
              </span>
              <p>{item.text}</p>
              <small>
                Recorded {new Date(item.recorded_at / 1000).toLocaleString()}
              </small>
            </div>
            <Button
              variant="outline"
              onClick={() => void open(item.id)}
              aria-label={`Open evidence: ${item.text.slice(0, 60)}`}
            >
              Open evidence
            </Button>
          </li>
        ))}
      </ul>
      {cursor && (
        <Button disabled={busy} onClick={() => void more()}>
          More memories
        </Button>
      )}
      {source && (
        <EvidencePanel
          key={source.id}
          source={source}
          nextOffset={source.next_offset}
          opening={opening}
          request={chatRequest}
          onOpen={open}
          onClose={() => {
            sourceGeneration.current++
            sourceAbort.current?.abort()
            setSource(null)
            setOpening(false)
          }}
          onViewProposal={setProposal}
          onViewReceipt={setReceipt}
          onSuggestReceipt={
            onProposeReceipt ? () => onProposeReceipt(source.id) : undefined
          }
        />
      )}
      {receipt && (
        <ReceiptProposalCard
          key={receipt}
          id={receipt}
          csrfToken={csrfToken}
          onOpen={open}
        />
      )}
      {proposal && (
        <AssetProposalCard
          key={proposal}
          id={proposal}
          request={chatRequest}
          onOpen={open}
        />
      )}
    </section>
  )
}
