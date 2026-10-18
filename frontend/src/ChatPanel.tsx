import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import './chat.css'
import { EvidencePanel, type EvidenceSource } from './EvidencePanel'
import { ChatRequestError as RequestError } from './chatRequest'

type Source = { id: string; text: string }
type Turn = {
  id: string
  request_id: string
  mode: string
  text: string
  state: string
  result: { text?: string; sources?: Source[] }
}
type Conversation = { id: string; title: string }
type Page<T> = { items: T[]; next_cursor: string | null }
type Credential = { id: string; kind: string; provider: string; label: string }

export function ChatPanel({
  csrfToken,
  refreshSession,
}: {
  csrfToken: string
  refreshSession?: () => Promise<void>
}) {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [conversationCursor, setConversationCursor] = useState<string | null>(
    null,
  )
  const [selected, setSelected] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [turnCursor, setTurnCursor] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [mode, setMode] = useState('save')
  const [credentials, setCredentials] = useState<Credential[]>([])
  const [credential, setCredential] = useState('')
  const [model, setModel] = useState('')
  const [consent, setConsent] = useState(false)
  const [usage, setUsage] = useState(0)
  const [busy, setBusy] = useState(false)
  const [retryNeeded, setRetryNeeded] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [source, setSource] = useState<EvidenceSource | null>(null)
  const [sourceOffset, setSourceOffset] = useState<number | null>(null)
  const [opening, setOpening] = useState(false)
  const abort = useRef<AbortController | null>(null)
  const pending = useRef<{
    conversation: string
    body: Record<string, string>
  } | null>(null)
  const generation = useRef(0)

  const request = useCallback(
    async (path: string, init?: RequestInit) => {
      const response = await fetch('/api/chat' + path, {
        ...init,
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
      })
      if (response.status === 401) {
        await refreshSession?.()
        throw new RequestError('Your session expired. Sign in again.', 401)
      }
      if (!response.ok)
        throw new RequestError(
          'Unable to load or save this conversation. Please try again.',
          response.status,
        )
      return response.json()
    },
    [csrfToken, refreshSession],
  )

  useEffect(() => {
    const controller = new AbortController()
    let alive = true
    async function load() {
      try {
        const [page, settings, entries, meter] = await Promise.all([
          request('/conversations', { signal: controller.signal }),
          fetch('/api/settings', {
            signal: controller.signal,
            cache: 'no-store',
          }).then((r) => r.json()),
          fetch('/api/credentials?limit=100', {
            signal: controller.signal,
            cache: 'no-store',
          }).then((r) => r.json()),
          request('/usage', { signal: controller.signal }),
        ])
        if (!alive) return
        setConversations(page.items)
        setConversationCursor(page.next_cursor)
        setConsent(settings.allow_external_ai === true)
        setCredentials(
          (entries.items ?? []).filter(
            (c: Credential) => c.kind === 'ai' && c.provider === 'openai',
          ),
        )
        setUsage(meter.requests)
      } catch {
        if (alive)
          setError('Unable to load chat. Please reopen Chat to try again.')
      } finally {
        if (alive) setLoading(false)
      }
    }
    void load()
    return () => {
      alive = false
      controller.abort()
      abort.current?.abort()
    }
  }, [request])

  async function openConversation(id: string) {
    const version = ++generation.current
    pending.current = null
    setRetryNeeded(false)
    setSource(null)
    setSelected(id)
    setTurns([])
    setTurnCursor(null)
    setError('')
    setLoading(true)
    try {
      const page: Page<Turn> = await request(`/conversations/${id}/turns`)
      if (version !== generation.current) return
      setTurns(page.items)
      setTurnCursor(page.next_cursor)
    } catch (caught) {
      if (version === generation.current) setError((caught as Error).message)
    } finally {
      if (version === generation.current) setLoading(false)
    }
  }

  async function moreConversations() {
    try {
      const page: Page<Conversation> = await request(
        `/conversations?cursor=${conversationCursor}`,
      )
      setConversations((current) => [...current, ...page.items])
      setConversationCursor(page.next_cursor)
    } catch (caught) {
      setError((caught as Error).message)
    }
  }

  async function moreTurns() {
    setLoading(true)
    try {
      const page: Page<Turn> = await request(
        `/conversations/${selected}/turns?cursor=${turnCursor}`,
      )
      setTurns((current) => [...current, ...page.items])
      setTurnCursor(page.next_cursor)
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setLoading(false)
    }
  }

  async function submit(event?: FormEvent) {
    event?.preventDefault()
    if (busy || turnCursor || !text.trim()) return
    setBusy(true)
    setError('')
    const controller = new AbortController()
    abort.current = controller
    try {
      let id = pending.current?.conversation || selected
      if (!id) {
        const created: Conversation = await request('/conversations', {
          method: 'POST',
          signal: controller.signal,
        })
        id = created.id
        setSelected(id)
        setConversations((current) => [created, ...current])
      }
      const body = pending.current?.body ?? {
        request_id: crypto.randomUUID(),
        mode,
        text,
        credential_id: credential,
        model,
      }
      pending.current = { conversation: id, body }
      setRetryNeeded(true)
      const turn: Turn = await request(`/conversations/${id}/turns`, {
        method: 'POST',
        body: JSON.stringify(body),
        signal: controller.signal,
      })
      setTurns((current) => [...current.filter((t) => t.id !== turn.id), turn])
      setConversations((current) =>
        current.map((c) =>
          c.id === id && c.title === 'New conversation'
            ? { ...c, title: body.text.slice(0, 60) }
            : c,
        ),
      )
      pending.current = null
      setRetryNeeded(false)
      setText('')
      const meter = await request('/usage')
      setUsage(meter.requests)
    } catch (caught) {
      if (caught instanceof RequestError) {
        pending.current = null
        setRetryNeeded(false)
        setError(caught.message)
      } else if ((caught as Error).name === 'AbortError')
        setError('Stopped. Reopen the conversation to check its saved status.')
      else
        setError(
          'Connection lost. Retry safely checks the saved request without duplicating saves or AI calls.',
        )
    } finally {
      setBusy(false)
      abort.current = null
    }
  }

  async function openSource(id: string, offset = 0) {
    setOpening(true)
    setError('')
    try {
      const original = await request(`/sources/${id}?offset=${offset}`)
      setSource(original)
      setSourceOffset(original.next_offset)
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setOpening(false)
    }
  }

  async function stop() {
    const running = pending.current
    try {
      if (running)
        await request(`/requests/${running.body.request_id}/cancel`, {
          method: 'POST',
        })
    } catch {
      setError(
        'Unable to confirm cancellation. Reopen the conversation to check its status.',
      )
    } finally {
      abort.current?.abort()
    }
  }

  return (
    <section className="chat-panel" aria-labelledby="chat-title">
      <div className="chat-heading">
        <div>
          <h1 id="chat-title">Chat</h1>
          <p>Keep the original. Find it again.</p>
        </div>
        <Button
          variant="outline"
          disabled={busy || loading}
          onClick={() => {
            generation.current++
            setSelected('')
            setTurns([])
            setTurnCursor(null)
            setSource(null)
            pending.current = null
            setRetryNeeded(false)
            setError('')
          }}
        >
          New conversation
        </Button>
      </div>
      <div className="chat-layout">
        <aside className="chat-conversations" aria-label="Conversations">
          <h2>Your conversations</h2>
          {!loading && !conversations.length && (
            <p>Your first conversation starts here.</p>
          )}
          {conversations.map((c) => (
            <Button
              key={c.id}
              variant="ghost"
              disabled={busy || loading}
              aria-current={selected === c.id ? 'true' : undefined}
              onClick={() => void openConversation(c.id)}
            >
              {c.title}
            </Button>
          ))}
          {conversationCursor && (
            <Button
              disabled={busy || loading}
              variant="outline"
              onClick={() => void moreConversations()}
            >
              More conversations
            </Button>
          )}
        </aside>
        <div className="chat-content">
          <div
            className="chat-messages"
            aria-live="polite"
            aria-busy={busy || loading}
          >
            {loading && <p role="status">Loading conversations…</p>}
            {!loading && !turns.length && (
              <div className="chat-empty">
                <h2>A place for the details</h2>
                <p>
                  Save a note in your own words, search using a few keywords, or
                  ask OpenAI about your saved evidence.
                </p>
                <p>
                  Saving and keyword search work without AI. Notes are original
                  statements; they do not create verified facts or inventory
                  items.
                </p>
              </div>
            )}
            {turns.map((turn) => (
              <article className="chat-turn" key={turn.id}>
                <p className="chat-label">
                  You ·{' '}
                  {turn.mode === 'save'
                    ? 'Save memory'
                    : turn.mode === 'search'
                      ? 'Keyword search'
                      : 'Ask OpenAI'}
                </p>
                <p className="chat-text">{turn.text}</p>
                <div className="chat-response">
                  <p className="chat-text">
                    {turn.result.text ||
                      (turn.state === 'pending'
                        ? 'This request may still be running. Reopen the conversation to check.'
                        : 'This request was interrupted. No automatic retry was made.')}
                  </p>
                  {turn.state === 'failed' && (
                    <p role="status">Request failed</p>
                  )}
                  {turn.result.sources?.map((s, i) => (
                    <Button
                      key={s.id}
                      variant="outline"
                      disabled={opening}
                      onClick={() => void openSource(s.id)}
                    >
                      Source {i + 1}: {s.text.slice(0, 55)}
                    </Button>
                  ))}
                </div>
              </article>
            ))}
            {turnCursor && (
              <Button
                disabled={loading || busy}
                onClick={() => void moreTurns()}
              >
                Load later messages
              </Button>
            )}
            {busy && (
              <p role="status">
                {mode === 'ask'
                  ? 'Searching your evidence and preparing an answer…'
                  : 'Saving your request…'}
              </p>
            )}
          </div>
          {source && (
            <EvidencePanel
              key={source.id}
              source={source}
              nextOffset={sourceOffset}
              opening={opening}
              onOpen={openSource}
              onClose={() => setSource(null)}
              request={request}
            />
          )}
          {error && (
            <p role="alert" className="chat-error">
              {error}
            </p>
          )}
          <form className="chat-composer" onSubmit={(e) => void submit(e)}>
            <label>
              Action
              <select
                value={mode}
                disabled={busy || retryNeeded}
                onChange={(e) => setMode(e.target.value)}
              >
                <option value="save">Save memory</option>
                <option value="search">Keyword search</option>
                <option value="ask">Ask OpenAI</option>
              </select>
            </label>
            {mode === 'ask' && (
              <div className="chat-provider">
                <p>
                  OpenAI receives your question, up to four recent user
                  messages, and matching evidence. {usage}/20 AI questions used
                  today (UTC). Provider charges may apply.
                </p>
                {!consent && (
                  <p>Enable external AI access in Settings to continue.</p>
                )}
                {!credentials.length && (
                  <p>
                    Add an AI credential with provider “openai” in Settings.
                  </p>
                )}
                <label>
                  OpenAI credential
                  <select
                    value={credential}
                    disabled={busy}
                    onChange={(e) => setCredential(e.target.value)}
                  >
                    <option value="">Choose a credential</option>
                    {credentials.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Model ID
                  <input
                    value={model}
                    disabled={busy}
                    maxLength={100}
                    placeholder="Enter a model available to your API account"
                    onChange={(e) => setModel(e.target.value)}
                  />
                </label>
              </div>
            )}
            <label htmlFor="chat-text">
              {mode === 'save'
                ? 'Memory to save'
                : mode === 'search'
                  ? 'Search keywords'
                  : 'Your question'}
            </label>
            <textarea
              id="chat-text"
              value={text}
              maxLength={mode === 'search' ? 200 : 4000}
              disabled={busy || retryNeeded}
              rows={3}
              onChange={(e) => setText(e.target.value)}
            />
            <p>
              {mode === 'search'
                ? 'Use 1–12 keywords. Every word must match.'
                : 'Only Save memory adds your original text to searchable memory.'}
            </p>
            <div className="chat-send">
              <Button
                type="submit"
                disabled={
                  busy ||
                  loading ||
                  !!turnCursor ||
                  !text.trim() ||
                  (mode === 'ask' &&
                    (!consent || !credential || !model || usage >= 20))
                }
              >
                {retryNeeded
                  ? 'Retry same request'
                  : mode === 'save'
                    ? 'Save memory'
                    : mode === 'search'
                      ? 'Search memories'
                      : 'Ask OpenAI'}
              </Button>
              {busy && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => void stop()}
                >
                  Stop
                </Button>
              )}
            </div>
          </form>
        </div>
      </div>
    </section>
  )
}
