import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type FormEvent,
} from 'react'
import { Button } from '@/components/ui/button'
import { Trash2 } from 'lucide-react'
import './chat.css'
import { contextKey, type WorkspaceContext } from './workspaceContext'
import { EvidencePanel, type EvidenceSource } from './EvidencePanel'
import { ReceiptProposalCard } from './ReceiptProposalCard'
import { AssetProposalCard } from './AssetProposalCard'
import { ChatRequestError as RequestError } from './chatRequest'
import { readChatStream } from './chatStream'
import { isAIProvider, aiProviderLabel } from './aiProviders'
import { ChatPhotoPicker, type SavedChatPhoto } from './ChatPhotoPicker'
import { ChatEmailScan, type EmailScanScope } from './ChatEmailScan'
import { ConversationDelete } from './ConversationDelete'

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
    scan_run_id?: string
    recall_limited?: boolean
    navigation?: { page: string; entity_id: string; name: string }
    choices?: { id: string; name: string }[]
    context?: WorkspaceContext
    changed_entity_id?: string
  }
}
type ChatBody = {
  request_id: string
  mode: string
  text: string
  credential_id: string
  model: string
  photo_id?: string
  source_id?: string
  scan?: EmailScanScope
  context?: WorkspaceContext
}

type Conversation = { id: string; title: string }
type Page<T> = { items: T[]; next_cursor: string | null }
type Credential = { id: string; kind: string; provider: string; label: string }

export function ChatPanel({
  csrfToken,
  refreshSession,
  initialReceiptSourceId = '',
  onOpenGraph,
  onOpenScan,
  onOpenAsset,
  onRecordChanged,
  context,
  contextLoading = false,
  compact = false,
  defaultMode = 'save',
}: {
  csrfToken: string
  initialReceiptSourceId?: string
  refreshSession?: () => Promise<void>
  onOpenGraph?: (id: string) => void
  onOpenScan?: (id: string) => void
  onOpenAsset?: (id: string) => void
  onRecordChanged?: (id: string) => void
  context?: WorkspaceContext | null
  contextLoading?: boolean
  compact?: boolean
  defaultMode?: string
}) {
  const contextNow = useRef(context)
  useLayoutEffect(() => {
    contextNow.current = context
  }, [context])
  const handledNavigation = useRef(new Set<string>())
  const [showConversations, setShowConversations] = useState(!compact)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [conversationCursor, setConversationCursor] = useState<string | null>(
    null,
  )
  const [paging, setPaging] = useState(false)
  const [selected, setSelected] = useState('')
  const [deletionTarget, setDeletionTarget] = useState<Conversation | null>(
    null,
  )
  const deletedConversations = useRef(new Set<string>())
  const deletionFocus = useRef<HTMLButtonElement | null>(null)
  const conversationToggle = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!deletionTarget && deletionFocus.current) {
      if (deletionFocus.current.isConnected) deletionFocus.current.focus()
      else conversationToggle.current?.focus()
      deletionFocus.current = null
    }
  }, [deletionTarget])
  const [turns, setTurns] = useState<Turn[]>([])
  const messages = useRef<HTMLDivElement>(null)
  const [turnCursor, setTurnCursor] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [mode, setMode] = useState(
    initialReceiptSourceId ? 'extract_receipt' : defaultMode,
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
  useEffect(() => {
    if (messages.current)
      messages.current.scrollTop = messages.current.scrollHeight
  }, [turns, draft])
  const [retryNeeded, setRetryNeeded] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [photo, setPhoto] = useState<SavedChatPhoto | null>(null)
  const [photoContext, setPhotoContext] = useState(0)
  const [scanScope, setScanScope] = useState<EmailScanScope | null>(null)
  const [source, setSource] = useState<EvidenceSource | null>(null)
  const [sourceOffset, setSourceOffset] = useState<number | null>(null)
  const [opening, setOpening] = useState(false)
  const abort = useRef<AbortController | null>(null)
  const pending = useRef<{
    conversation: string
    body: ChatBody
  } | null>(null)
  const generation = useRef(0)
  const sourceGeneration = useRef(0)
  const initialSourceAbort = useRef<AbortController | null>(null)
  const dismissedInitialSource = useRef('')
  const usageRead = useRef<AbortController | null>(null)
  const conversationPage = useRef<AbortController | null>(null)
  const usesAI = [
    'ask',
    'extract',
    'extract_receipt',
    'extract_photo',
    'extract_photo_receipt',
  ].includes(mode)
  const usesPhoto = mode === 'extract_photo' || mode === 'extract_photo_receipt'
  const usesScan = mode === 'scan_email'

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
    if (
      !initialReceiptSourceId ||
      dismissedInitialSource.current === initialReceiptSourceId
    )
      return
    const controller = new AbortController()
    initialSourceAbort.current = controller
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
    conversationPage.current?.abort()
    conversationPage.current = null
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
        if (!Array.isArray(page.items))
          throw new Error('Invalid conversation page')
        setConversations(
          page.items.filter(
            (row: Conversation) => !deletedConversations.current.has(row.id),
          ),
        )
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
        if (alive) {
          setPaging(false)
          setLoading(false)
        }
      }
    }
    void load()
    return () => {
      alive = false
      controller.abort()
      abort.current?.abort()
      choiceAbort.current?.abort()
      usageRead.current?.abort()
      conversationPage.current?.abort()
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
    if (deletionTarget || deletedConversations.current.has(id)) return
    cancelContextReads()
    setScanScope(null)
    const version = ++generation.current
    pending.current = null
    setRetryNeeded(false)
    setPhoto(null)
    setPhotoContext((value) => value + 1)
    setNotice('')
    clearEvidence()
    setViewProposal('')
    setViewReceipt('')
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
    if (busy || loading || conversationPage.current || !conversationCursor)
      return
    const controller = new AbortController()
    conversationPage.current = controller
    const version = generation.current
    setPaging(true)
    try {
      const page: Page<Conversation> = await request(
        `/conversations?cursor=${conversationCursor}`,
        { signal: controller.signal },
      )
      if (controller.signal.aborted) return
      setConversations((current) => {
        const known = new Set(current.map((row) => row.id))
        const next = [...current]
        for (const row of page.items) {
          if (!known.has(row.id) && !deletedConversations.current.has(row.id)) {
            known.add(row.id)
            next.push(row)
          }
        }
        return next
      })
      setConversationCursor(page.next_cursor)
    } catch (caught) {
      if (!controller.signal.aborted && version === generation.current)
        setError((caught as Error).message)
    } finally {
      if (conversationPage.current === controller) {
        conversationPage.current = null
        setPaging(false)
      }
    }
  }

  function cancelContextReads() {
    cancelInitialSelection()
    usageRead.current?.abort()
    conversationPage.current?.abort()
    conversationPage.current = null
    setPaging(false)
  }

  function cancelInitialSelection() {
    dismissedInitialSource.current = initialReceiptSourceId
    initialSourceAbort.current?.abort()
  }

  async function refreshUsage() {
    usageRead.current?.abort()
    const controller = new AbortController()
    usageRead.current = controller
    const version = generation.current
    try {
      const meter = await request('/usage', { signal: controller.signal })
      if (!controller.signal.aborted && version === generation.current)
        setUsage(meter.requests)
    } catch {
      if (!controller.signal.aborted && version === generation.current)
        setNotice(
          'Request saved. Daily usage could not be refreshed; reopen Chat to check it.',
        )
    } finally {
      if (usageRead.current === controller) usageRead.current = null
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

  async function submit(event: FormEvent, submittedAt: number) {
    event?.preventDefault()
    if (
      busy ||
      deletionTarget ||
      savingChoice ||
      loading ||
      turnCursor ||
      contextLoading ||
      (usesScan ? !scanScope : usesPhoto ? !photo : !text.trim())
    )
      return
    const sentContext = context
      ? {
          page: context.page,
          entity_id: context.entity_id,
          version: context.version,
        }
      : undefined
    setBusy(true)
    cancelContextReads()
    setDraft('')
    setError('')
    setNotice('')
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
      const body: ChatBody = pending.current?.body ?? {
        request_id: crypto.randomUUID(),
        mode,
        ...(sentContext ? { context: sentContext } : {}),
        text: usesScan
          ? 'Scan connected email for original text evidence.'
          : usesPhoto
            ? mode === 'extract_photo_receipt'
              ? 'Read receipt lines in this photo for human review.'
              : 'Read this photo for a reviewed asset proposal.'
            : text,
        credential_id: usesScan ? '' : credential,
        model: usesScan ? '' : model,
        ...(usesScan
          ? {
              scan: {
                ...scanScope!,
                until_timestamp: Math.min(
                  scanScope!.until_timestamp,
                  submittedAt,
                ),
              },
            }
          : {}),
        ...(usesPhoto ? { photo_id: photo!.id } : {}),
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
      if (turn.state === 'pending') {
        setNotice(
          'This request is still running. Retry the same request to check its saved result.',
        )
        return
      }
      if (
        turn.state === 'complete' &&
        !handledNavigation.current.has(turn.request_id)
      ) {
        handledNavigation.current.add(turn.request_id)
        if (contextKey(contextNow.current) === contextKey(body.context)) {
          if (turn.result.navigation)
            onOpenAsset?.(turn.result.navigation.entity_id)
          if (turn.result.changed_entity_id)
            onRecordChanged?.(turn.result.changed_entity_id)
        }
      }
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
      if (
        body.mode === 'extract_photo' ||
        body.mode === 'extract_photo_receipt'
      )
        setPhoto(null)
      else if (body.mode === 'scan_email') {
        setScanScope(null)
        setPhotoContext((value) => value + 1)
      } else setText('')
      void refreshUsage()
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

  function clearEvidence() {
    ++sourceGeneration.current
    setSource(null)
    setSourceOffset(null)
    setOpening(false)
  }
  const invalidateEvidence = useCallback(() => {
    ++sourceGeneration.current
  }, [])
  useEffect(() => invalidateEvidence, [invalidateEvidence])

  async function openSource(id: string, offset = 0) {
    if (loading) return
    const conversationVersion = generation.current
    const sourceVersion = ++sourceGeneration.current
    const current = () =>
      conversationVersion === generation.current &&
      sourceVersion === sourceGeneration.current
    setOpening(true)
    setError('')
    try {
      const original = await request(`/sources/${id}?offset=${offset}`)
      if (!current()) return
      setSource(original)
      setSourceOffset(original.next_offset)
    } catch (caught) {
      if (current()) setError((caught as Error).message)
    } finally {
      if (current()) setOpening(false)
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

  function conversationDeleted(id: string) {
    deletedConversations.current.add(id)
    conversationPage.current?.abort()
    conversationPage.current = null
    setPaging(false)
    setConversations((current) => current.filter((row) => row.id !== id))
    if (selected === id) {
      cancelContextReads()
      generation.current++
      abort.current?.abort()
      pending.current = null
      setRetryNeeded(false)
      setSelected('')
      setTurns([])
      setTurnCursor(null)
      setDraft('')
      clearEvidence()
      setViewProposal('')
      setViewReceipt('')
      setError('')
    }
    setNotice('Conversation deleted. Other saved records were retained.')
    setDeletionTarget(null)
  }

  return (
    <section className="chat-panel" aria-labelledby="chat-title">
      <div className="chat-heading">
        <div>
          {compact ? (
            <h2 id="chat-title">Your personal assistant</h2>
          ) : (
            <h1 id="chat-title">Chat</h1>
          )}
          {context && (
            <p className="chat-context">
              Context: {context.page}
              {context.name ? ` / ${context.name}` : ''}
            </p>
          )}
          {contextLoading && <p role="status">Updating page context…</p>}
          {!compact && <p>Keep the original. Find it again.</p>}
        </div>
        <Button
          variant="outline"
          disabled={busy || loading || !!deletionTarget}
          onClick={() => {
            cancelContextReads()
            generation.current++
            setScanScope(null)
            setSelected('')
            setTurns([])
            setTurnCursor(null)
            clearEvidence()
            setViewProposal('')
            setViewReceipt('')
            pending.current = null
            setRetryNeeded(false)
            setPhoto(null)
            setPhotoContext((value) => value + 1)
            setNotice('')
            setError('')
          }}
        >
          New conversation
        </Button>
      </div>
      <Button
        ref={conversationToggle}
        variant="ghost"
        aria-expanded={showConversations}
        disabled={!!deletionTarget}
        onClick={() => setShowConversations((value) => !value)}
      >
        {showConversations ? 'Hide conversations' : 'Your conversations'}
      </Button>
      <div
        className={`chat-layout ${showConversations && !deletionTarget ? '' : 'conversations-hidden'}`}
      >
        <aside
          className="chat-conversations"
          aria-label="Conversations"
          hidden={!showConversations || !!deletionTarget}
        >
          <h2>Your conversations</h2>
          {!loading && !conversations.length && (
            <p>Your first conversation starts here.</p>
          )}
          {conversations.map((c) => (
            <div className="chat-conversation-row" key={c.id}>
              <Button
                variant="ghost"
                disabled={busy || loading || !!deletionTarget}
                aria-current={selected === c.id ? 'true' : undefined}
                onClick={() => void openConversation(c.id)}
              >
                {c.title}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="conversation-delete-action"
                disabled={busy || loading || !!deletionTarget}
                aria-label={`Review deletion of ${c.title}`}
                onClick={(event) => {
                  deletionFocus.current = event.currentTarget
                  conversationPage.current?.abort()
                  conversationPage.current = null
                  setPaging(false)
                  setDeletionTarget(c)
                }}
              >
                <Trash2 aria-hidden="true" />
              </Button>
            </div>
          ))}
          {conversationCursor && (
            <Button
              disabled={busy || loading || paging || !!deletionTarget}
              variant="outline"
              onClick={() => void moreConversations()}
            >
              More conversations
            </Button>
          )}
          {paging && <p role="status">Loading more conversations…</p>}
        </aside>
        <div className="chat-content">
          {deletionTarget && (
            <ConversationDelete
              key={deletionTarget.id}
              id={deletionTarget.id}
              title={deletionTarget.title}
              request={request}
              onDeleted={conversationDeleted}
              onCancel={() => setDeletionTarget(null)}
            />
          )}
          <div className="chat-saved-content" hidden={!!deletionTarget}>
            <div
              className="chat-messages"
              ref={messages}
              aria-live="polite"
              aria-busy={busy || loading}
            >
              {loading && <p role="status">Loading conversations…</p>}
              {!loading && !turns.length && (
                <div className="chat-empty">
                  <h2>A place for the details</h2>
                  <p>
                    Save a note in your own words, search using a few keywords,
                    or ask OpenAI, Claude or Google Gemini about your saved
                    evidence.
                  </p>
                  <p>
                    Saving and keyword search work without AI. Notes are
                    original statements; they do not create verified facts or
                    inventory items.
                  </p>
                </div>
              )}
              {turns.map((turn) => (
                <article className="chat-turn" key={turn.id}>
                  <p className="chat-label">
                    You ·{' '}
                    {turn.mode === 'organize'
                      ? 'Assistant'
                      : turn.mode === 'save'
                        ? 'Save memory'
                        : turn.mode === 'search'
                          ? 'Keyword search'
                          : turn.mode === 'extract' ||
                              turn.mode === 'extract_receipt'
                            ? turn.mode === 'extract_receipt'
                              ? 'Suggest receipt items'
                              : 'Suggest asset'
                            : turn.mode === 'scan_email'
                              ? 'Request email scan'
                              : turn.mode === 'extract_photo_receipt'
                                ? 'Review receipt photo'
                                : turn.mode === 'extract_photo'
                                  ? 'Read photo'
                                  : 'Ask AI'}
                  </p>
                  <p className="chat-text">{turn.text}</p>
                  <div className="chat-response">
                    {turn.result.context?.name && (
                      <p>For {turn.result.context.name}</p>
                    )}
                    {turn.result.navigation && (
                      <Button
                        variant="outline"
                        onClick={() =>
                          onOpenAsset?.(turn.result.navigation!.entity_id)
                        }
                      >
                        Open {turn.result.navigation.name}
                      </Button>
                    )}
                    {turn.result.choices?.map((item, index) => (
                      <Button
                        key={item.id}
                        variant="outline"
                        onClick={() => onOpenAsset?.(item.id)}
                      >
                        Open {item.name} (record {index + 1})
                      </Button>
                    ))}
                    {turn.result.scan_run_id && (
                      <Button
                        variant="outline"
                        disabled={!onOpenScan}
                        onClick={() => onOpenScan?.(turn.result.scan_run_id!)}
                      >
                        View email scan
                      </Button>
                    )}
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
                        onClick={() =>
                          setViewProposal(turn.result.proposal_id!)
                        }
                      >
                        View asset proposal
                      </Button>
                    )}
                    {turn.result.sources?.map((s, i) => (
                      <Button
                        key={s.id}
                        variant="outline"
                        disabled={opening || loading}
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
                  {mode === 'extract' || mode === 'extract_receipt' || usesPhoto
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
                onClose={clearEvidence}
                request={request}
                onViewReceipt={setViewReceipt}
                onSuggestReceipt={
                  busy || retryNeeded
                    ? undefined
                    : () => {
                        cancelInitialSelection()
                        setExtractSource(source.id)
                        setText(source.text)
                        setMode('extract_receipt')
                        clearEvidence()
                        setViewReceipt('')
                      }
                }
                onViewProposal={(id) => setViewProposal(id)}
                onSuggest={
                  busy || retryNeeded
                    ? undefined
                    : () => {
                        cancelInitialSelection()
                        setExtractSource(source.id)
                        setText(source.text)
                        setMode('extract')
                        clearEvidence()
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
            {notice && <p role="status">{notice}</p>}
            <form
              className="chat-composer"
              onSubmit={(e) => void submit(e, Math.floor(Date.now() / 1000))}
            >
              <label>
                Action
                <select
                  value={mode}
                  disabled={busy || retryNeeded}
                  onChange={(e) => {
                    cancelInitialSelection()
                    setScanScope(null)
                    setMode(e.target.value)
                  }}
                >
                  <option value="organize">Assistant</option>
                  <option value="save">Save memory</option>
                  <option value="search">Keyword search</option>
                  <option value="scan_email">Request an email scan</option>
                  <option value="ask">Ask AI</option>
                  <option value="extract_photo">Read a saved photo</option>
                  <option value="extract_photo_receipt">
                    Review a receipt photo
                  </option>
                  <option value="extract_receipt" disabled={!extractSource}>
                    Review multiple items from selected note
                  </option>
                  <option value="extract" disabled={!extractSource}>
                    Suggest asset from selected note
                  </option>
                </select>
              </label>
              {usesScan && (
                <ChatEmailScan
                  key={photoContext}
                  disabled={busy || retryNeeded || loading}
                  onChange={setScanScope}
                />
              )}
              {usesPhoto && (
                <ChatPhotoPicker
                  key={`${selected}:${photoContext}`}
                  csrfToken={csrfToken}
                  selected={photo}
                  onSelect={setPhoto}
                  disabled={busy || retryNeeded || loading}
                />
              )}
              {usesAI && (
                <div className="chat-provider">
                  <p>
                    {mode === 'extract_photo_receipt'
                      ? 'Your selected provider receives the selected original photo, or its current saved transcription if already read. Receipt suggestions and transcription are unverified; inspect every line and quantity before confirming inventory. At most eight lines and twenty total units are reviewed.'
                      : mode === 'extract_photo'
                        ? 'Your selected provider receives the selected original photo. The reading is unverified and proposes at most one item; review it before adding anything to inventory.'
                        : mode === 'extract' || mode === 'extract_receipt'
                          ? 'Your selected provider receives only the selected saved note. Nothing enters inventory until you review and confirm the proposed items.'
                          : 'Your selected provider receives your question, up to four recent user messages, matching evidence, relevant records and requested graph connections.'}{' '}
                    {usage}/20 AI requests used today (UTC). Provider charges
                    may apply.
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
              {!usesPhoto && !usesScan && (
                <>
                  <label htmlFor="chat-text">
                    {mode === 'organize'
                      ? 'Message your assistant'
                      : mode === 'save'
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
                    onChange={(e) => {
                      cancelInitialSelection()
                      setText(e.target.value)
                    }}
                  />
                  <p>
                    {mode === 'organize'
                      ? 'Try “Edit my F150”, then ‘Set custom "Tire size" to 205/55R16’ while viewing it. Supplied details keep evidence and history. Choose Ask AI for other questions.'
                      : mode === 'search'
                        ? 'Use 1–12 keywords. Every word must match.'
                        : mode === 'extract' || mode === 'extract_receipt'
                          ? 'Review the proposal before creating an asset. Correct the saved note first if its text is wrong.'
                          : 'Only Save memory adds your original text to searchable memory.'}
                  </p>
                </>
              )}
              <div className="chat-send">
                <Button
                  type="submit"
                  disabled={
                    busy ||
                    savingChoice ||
                    loading ||
                    !!turnCursor ||
                    contextLoading ||
                    (usesScan
                      ? !scanScope
                      : usesPhoto
                        ? !photo
                        : !text.trim()) ||
                    (usesAI &&
                      (!consent || !credential || !model || usage >= 20))
                  }
                >
                  {retryNeeded
                    ? 'Retry same request'
                    : mode === 'organize'
                      ? 'Send'
                      : mode === 'save'
                        ? 'Save memory'
                        : mode === 'search'
                          ? 'Search memories'
                          : usesScan
                            ? 'Start email scan'
                            : mode === 'extract_photo_receipt'
                              ? 'Review receipt photo'
                              : mode === 'extract_photo'
                                ? 'Read selected photo'
                                : mode === 'extract' ||
                                    mode === 'extract_receipt'
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
      </div>
    </section>
  )
}
