import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import './chat.css'
import { EvidencePanel, type EvidenceSource } from './EvidencePanel'
import { ReceiptProposalCard } from './ReceiptProposalCard'
import { AssetProposalCard } from './AssetProposalCard'
import { ChatRequestError as RequestError } from './chatRequest'
import { readChatStream } from './chatStream'
import { isAIProvider, aiProviderLabel } from './aiProviders'

type Source = { id: string; text: string }
type Turn = {
  id: string
  request_id: string
  mode: string
  text: string
  state: string
  result: {
    text?: string
    sources?: Source[]
    receipt_proposal_id?: string
    proposal_id?: string
    provider?: string
    model?: string
    records?: { id: string; name: string; kind: string }[]
    recall_limited?: boolean
  }
}
type Conversation = { id: string; title: string }
type Page<T> = { items: T[]; next_cursor: string | null }
type Credential = { id: string; kind: string; provider: string; label: string }

export function ChatPanel({
  csrfToken,
  refreshSession,
  initialReceiptSourceId = '',
  onOpenGraph,
}: {
  csrfToken: string
  initialReceiptSourceId?: string
  refreshSession?: () => Promise<void>
  onOpenGraph?: (id: string) => void
}) {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [conversationCursor, setConversationCursor] = useState<string | null>(
    null,
  )
  const [selected, setSelected] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [turnCursor, setTurnCursor] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [mode, setMode] = useState(
    initialReceiptSourceId ? 'extract_receipt' : 'save',
  )
  const [extractSource, setExtractSource] = useState('')
  const [viewProposal, setViewProposal] = useState('')
  const [viewReceipt, setViewReceipt] = useState('')
  const [credentials, setCredentials] = useState<Credential[]>([])
  const [credential, setCredential] = useState('')
  const [model, setModel] = useState('')
  const [savingChoice, setSavingChoice] = useState(false)
  const [choiceNotice, setChoiceNotice] = useState('')
  const choiceAbort = useRef<AbortController | null>(null)
  const [consent, setConsent] = useState(false)
  const [usage, setUsage] = useState(0)
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState('')
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
    if (!initialReceiptSourceId) return
    const controller = new AbortController()
    void request('/sources/' + initialReceiptSourceId, {
      signal: controller.signal,
    })
      .then((row) => {
        if (controller.signal.aborted) return
        if (!row.note?.is_current)
          throw new Error('Choose the current saved note first.')
        setExtractSource(row.id)
        setText(row.text)
        setMode('extract_receipt')
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError(
            'Unable to select this receipt source. Open the current note in Memories and try again.',
          )
      })
    return () => controller.abort()
  }, [initialReceiptSourceId, request])

  useEffect(() => {
    const controller = new AbortController()
    let alive = true
    async function load() {
      try {
        const [page, settings, entries, meter, choice] = await Promise.all([
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
          request('/preferences', { signal: controller.signal }),
        ])
        if (!alive) return
        setConversations(page.items)
        setConversationCursor(page.next_cursor)
        setConsent(settings.allow_external_ai === true)
        setCredentials(
          (entries.items ?? []).filter(
            (c: Credential) => c.kind === 'ai' && isAIProvider(c.provider),
          ),
        )
        setUsage(meter.requests)
        const saved = (entries.items ?? []).find(
          (c: Credential) =>
            c.id === choice.credential_id &&
            c.kind === 'ai' &&
            isAIProvider(c.provider),
        )
        setCredential(saved?.id ?? '')
        setModel(saved ? choice.model : '')
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
      choiceAbort.current?.abort()
    }
  }, [request])

  async function saveChoice(clear = false) {
    if (savingChoice) return
    const controller = new AbortController()
    choiceAbort.current = controller
    setSavingChoice(true)
    setChoiceNotice('')
    try {
      const response = await fetch('/api/chat/preferences', {
        method: 'PUT',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify({
          credential_id: clear ? '' : credential,
          model: clear ? '' : model,
        }),
        signal: controller.signal,
      })
      if (response.status === 401) await refreshSession?.()
      if (!response.ok) throw new Error('Unable to save your AI choice.')
      if (controller.signal.aborted) return
      if (clear) {
        setCredential('')
        setModel('')
      }
      setChoiceNotice(
        clear
          ? 'Saved AI choice cleared.'
          : 'AI choice saved for your account.',
      )
    } catch {
      if (!controller.signal.aborted)
        setChoiceNotice('Unable to save your AI choice. Please try again.')
    } finally {
      if (!controller.signal.aborted) setSavingChoice(false)
    }
  }

  async function openConversation(id: string) {
    const version = ++generation.current
    pending.current = null
    setRetryNeeded(false)
    setSource(null)
    setViewProposal('')
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
    if (busy || savingChoice || turnCursor || !text.trim()) return
    setBusy(true)
    setDraft('')
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
        ...(mode === 'extract' || mode === 'extract_receipt'
          ? { source_id: extractSource }
          : {}),
      }
      pending.current = { conversation: id, body }
      setRetryNeeded(true)
      let turn: Turn
      if (body.mode === 'ask') {
        const response = await fetch(`/api/chat/conversations/${id}/stream`, {
          method: 'POST',
          credentials: 'same-origin',
          cache: 'no-store',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrfToken,
          },
          body: JSON.stringify(body),
          signal: controller.signal,
        })
        if (response.status === 401) await refreshSession?.()
        if (!response.ok)
          throw new RequestError(
            'Unable to start this reply. Please try again.',
            response.status,
          )
        turn = await readChatStream<Turn>(response, setDraft)
      } else {
        turn = await request(`/conversations/${id}/turns`, {
          method: 'POST',
          body: JSON.stringify(body),
          signal: controller.signal,
        })
      }
      setTurns((current) => [...current.filter((t) => t.id !== turn.id), turn])
      if (turn.result.receipt_proposal_id)
        setViewReceipt(turn.result.receipt_proposal_id)
      if (turn.result.proposal_id) setViewProposal(turn.result.proposal_id)
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
      setDraft('')
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
                  ask OpenAI, Claude or Google Gemini about your saved evidence.
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
                      : turn.mode === 'extract' ||
                          turn.mode === 'extract_receipt'
                        ? turn.mode === 'extract_receipt'
                          ? 'Suggest receipt items'
                          : 'Suggest asset'
                        : turn.mode === 'extract_photo'
                          ? 'Read photo'
                          : 'Ask AI'}
                </p>
                <p className="chat-text">{turn.text}</p>
                <div className="chat-response">
                  {turn.result.provider && (
                    <p className="chat-label">
                      {aiProviderLabel(turn.result.provider)} ·{' '}
                      {turn.result.model}
                    </p>
                  )}
                  <p className="chat-text">
                    {turn.result.text ||
                      (turn.state === 'pending'
                        ? 'This request may still be running. Reopen the conversation to check.'
                        : 'This request was interrupted. No automatic retry was made.')}
                  </p>
                  {turn.state === 'failed' && (
                    <p role="status">Request failed</p>
                  )}
                  {!!turn.result.records?.length && (
                    <div className="chat-records">
                      <p>Records inspected</p>
                      {turn.result.records.map((record, index) =>
                        onOpenGraph ? (
                          <Button
                            key={record.id}
                            variant="outline"
                            onClick={() => onOpenGraph(record.id)}
                            aria-label={`Open ${record.name} in graph (record ${index + 1})`}
                          >
                            {record.name} · {record.kind}
                          </Button>
                        ) : (
                          <p key={record.id}>
                            {record.name} · {record.kind}
                          </p>
                        ),
                      )}
                    </div>
                  )}
                  {turn.result.recall_limited && (
                    <p>
                      This reply used a limited selection of records. Other
                      evidence may exist.
                    </p>
                  )}
                  {turn.result.receipt_proposal_id && (
                    <Button
                      variant="outline"
                      onClick={() =>
                        setViewReceipt(turn.result.receipt_proposal_id!)
                      }
                    >
                      View receipt review
                    </Button>
                  )}
                  {turn.result.proposal_id && (
                    <Button
                      variant="outline"
                      onClick={() => setViewProposal(turn.result.proposal_id!)}
                    >
                      View asset proposal
                    </Button>
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
            {draft && (
              <section className="chat-draft" aria-label="Reply draft">
                <p className="chat-label">
                  Generating · draft not yet validated or saved
                </p>
                <p className="chat-text">{draft}</p>
              </section>
            )}
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
                {mode === 'extract' || mode === 'extract_receipt'
                  ? 'Preparing a proposal for your review…'
                  : mode === 'ask'
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
              onViewReceipt={setViewReceipt}
              onSuggestReceipt={
                busy || retryNeeded
                  ? undefined
                  : () => {
                      setExtractSource(source.id)
                      setText(source.text)
                      setMode('extract_receipt')
                      setSource(null)
                      setViewReceipt('')
                    }
              }
              onViewProposal={(id) => setViewProposal(id)}
              onSuggest={
                busy || retryNeeded
                  ? undefined
                  : () => {
                      setExtractSource(source.id)
                      setText(source.text)
                      setMode('extract')
                      setSource(null)
                      setViewProposal('')
                    }
              }
            />
          )}
          {viewReceipt && (
            <ReceiptProposalCard
              key={viewReceipt}
              id={viewReceipt}
              csrfToken={csrfToken}
              onOpen={openSource}
            />
          )}
          {viewProposal && (
            <AssetProposalCard
              key={viewProposal}
              id={viewProposal}
              request={request}
              onOpen={openSource}
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
                <option value="ask">Ask AI</option>
                <option value="extract_receipt" disabled={!extractSource}>
                  Review multiple items from selected note
                </option>
                <option value="extract" disabled={!extractSource}>
                  Suggest asset from selected note
                </option>
              </select>
            </label>
            {(mode === 'ask' ||
              mode === 'extract' ||
              mode === 'extract_receipt') && (
              <div className="chat-provider">
                <p>
                  {mode === 'extract' || mode === 'extract_receipt'
                    ? 'Your selected provider receives only the selected saved note. Nothing enters inventory until you review and confirm the proposed items.'
                    : 'Your selected provider receives your question, up to four recent user messages, matching evidence, relevant records and requested graph connections.'}{' '}
                  {usage}/20 AI requests used today (UTC). Provider charges may
                  apply.
                </p>
                {!consent && (
                  <p>Enable external AI access in Settings to continue.</p>
                )}
                {!credentials.length && (
                  <p>
                    Add an AI connection with provider “openai”, “anthropic”
                    (Claude) or “google” (Gemini) in Settings.
                  </p>
                )}
                <label>
                  AI connection
                  <select
                    value={credential}
                    disabled={busy || savingChoice || retryNeeded || loading}
                    onChange={(e) => {
                      setCredential(e.target.value)
                      setModel('')
                      setChoiceNotice('')
                    }}
                  >
                    <option value="">Choose a credential</option>
                    {credentials.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.label} · {aiProviderLabel(c.provider)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Model ID
                  <input
                    value={model}
                    disabled={busy || savingChoice || retryNeeded || loading}
                    maxLength={100}
                    placeholder="Enter a model available to your API account"
                    onChange={(e) => {
                      setModel(e.target.value)
                      setChoiceNotice('')
                    }}
                  />
                </label>
                <div className="chat-send">
                  <Button
                    type="button"
                    variant="outline"
                    disabled={
                      busy ||
                      loading ||
                      savingChoice ||
                      retryNeeded ||
                      !credential ||
                      !model
                    }
                    onClick={() => void saveChoice()}
                  >
                    Remember AI choice
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={busy || loading || savingChoice || retryNeeded}
                    onClick={() => void saveChoice(true)}
                  >
                    Forget saved AI choice
                  </Button>
                </div>
                <p>
                  Remembering a choice does not enable external AI or send any
                  records.
                </p>
                {choiceNotice && <p role="status">{choiceNotice}</p>}
              </div>
            )}
            <label htmlFor="chat-text">
              {mode === 'save'
                ? 'Memory to save'
                : mode === 'search'
                  ? 'Search keywords'
                  : mode === 'extract' || mode === 'extract_receipt'
                    ? 'Selected saved note'
                    : 'Your question'}
            </label>
            <textarea
              id="chat-text"
              value={text}
              maxLength={mode === 'search' ? 200 : 4000}
              disabled={busy || retryNeeded}
              readOnly={mode === 'extract' || mode === 'extract_receipt'}
              rows={3}
              onChange={(e) => setText(e.target.value)}
            />
            <p>
              {mode === 'search'
                ? 'Use 1–12 keywords. Every word must match.'
                : mode === 'extract' || mode === 'extract_receipt'
                  ? 'Review the proposal before creating an asset. Correct the saved note first if its text is wrong.'
                  : 'Only Save memory adds your original text to searchable memory.'}
            </p>
            <div className="chat-send">
              <Button
                type="submit"
                disabled={
                  busy ||
                  savingChoice ||
                  loading ||
                  !!turnCursor ||
                  !text.trim() ||
                  ((mode === 'ask' ||
                    mode === 'extract' ||
                    mode === 'extract_receipt') &&
                    (!consent || !credential || !model || usage >= 20))
                }
              >
                {retryNeeded
                  ? 'Retry same request'
                  : mode === 'save'
                    ? 'Save memory'
                    : mode === 'search'
                      ? 'Search memories'
                      : mode === 'extract' || mode === 'extract_receipt'
                        ? mode === 'extract_receipt'
                          ? 'Suggest receipt items'
                          : 'Suggest asset'
                        : 'Ask AI'}
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
