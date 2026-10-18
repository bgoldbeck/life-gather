import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { AssetProposalCard } from './AssetProposalCard'
import { EvidencePanel, type EvidenceSource } from './EvidencePanel'
import { ChatRequestError } from './chatRequest'
import './photos.css'

type Photo = {
  id: string
  filename: string
  purpose: string
  size: number
  width: number
  height: number
  updated_at: number
  source_id: string | null
  deleted_at: number | null
}
type Credential = { id: string; kind: string; provider: string; label: string }
type Pending = { conversation: string; body: Record<string, string> }

export function PhotosPanel({
  csrfToken,
  assetId = '',
}: {
  csrfToken: string
  assetId?: string
}) {
  const [items, setItems] = useState<Photo[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [selected, setSelected] = useState<Photo | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [purpose, setPurpose] = useState('photo')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [credentials, setCredentials] = useState<Credential[]>([])
  const [credential, setCredential] = useState('')
  const [model, setModel] = useState('')
  const [consent, setConsent] = useState(false)
  const [proposal, setProposal] = useState('')
  const [source, setSource] = useState<EvidenceSource | null>(null)
  const [deleteAcknowledged, setDeleteAcknowledged] = useState(false)
  const [retry, setRetry] = useState(false)
  const pending = useRef<Pending | null>(null)
  const uploadInput = useRef<HTMLInputElement>(null)
  const request = useCallback(
    async (path: string, init?: RequestInit) => {
      const response = await fetch('/api/' + path, {
        ...init,
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
          ...init?.headers,
        },
      })
      if (!response.ok)
        throw new ChatRequestError(
          'Unable to complete this request. Check the file, session and settings, then try again.',
          response.status,
        )
      return response.json()
    },
    [csrfToken],
  )
  const chatRequest = useCallback(
    (path: string, init?: RequestInit) => request('chat' + path, init),
    [request],
  )
  const load = useCallback(
    async (next = '') => {
      const page = await request(
        `photos?asset_id=${encodeURIComponent(assetId)}&cursor=${next}`,
      )
      setItems((current) => (next ? [...current, ...page.items] : page.items))
      setCursor(page.next_cursor)
    },
    [request, assetId],
  )
  useEffect(() => {
    let alive = true
    const controller = new AbortController()
    void Promise.all([
      request(`photos?asset_id=${encodeURIComponent(assetId)}`, {
        signal: controller.signal,
      }),
      request('credentials?limit=100', { signal: controller.signal }),
      request('settings', { signal: controller.signal }),
    ])
      .then(([page, entries, settings]) => {
        if (!alive) return
        setItems(page.items)
        setCursor(page.next_cursor)
        setCredentials(
          (entries.items ?? []).filter(
            (c: Credential) =>
              c.kind === 'ai' && ['openai', 'anthropic'].includes(c.provider),
          ),
        )
        setConsent(settings.allow_external_ai === true)
      })
      .catch(() => {
        if (alive) setError('Unable to load photos. Reopen this view to retry.')
      })
    return () => {
      alive = false
      controller.abort()
    }
  }, [request, assetId])

  async function upload(event: FormEvent) {
    event.preventDefault()
    if (!file || busy) return
    if (file.size > 8 * 1024 * 1024) {
      setError('Choose a photo no larger than 8 MiB.')
      return
    }
    setBusy(true)
    setError('')
    setStatus('')
    try {
      const row = await request(
        `photos?purpose=${purpose}&asset_id=${encodeURIComponent(assetId)}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/octet-stream',
            'X-File-Name': encodeURIComponent(file.name),
          },
          body: file,
        },
      )
      setSelected(row)
      setDeleteAcknowledged(false)
      setProposal('')
      setSource(null)
      setFile(null)
      if (uploadInput.current) uploadInput.current.value = ''
      await load()
      setStatus('Photo saved privately. No AI request was made.')
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setBusy(false)
    }
  }
  async function openSource(id: string) {
    setError('')
    try {
      setSource(await chatRequest('/sources/' + id))
    } catch (caught) {
      setError((caught as Error).message)
    }
  }
  async function read() {
    if (!selected || busy) return
    setBusy(true)
    setError('')
    setStatus('')
    try {
      if (!pending.current) {
        const conversation = await chatRequest('/conversations', {
          method: 'POST',
        })
        pending.current = {
          conversation: conversation.id,
          body: {
            request_id: crypto.randomUUID(),
            mode: 'extract_photo',
            photo_id: selected.id,
            text: 'Read this photo for a reviewed asset proposal.',
            credential_id: credential,
            model,
          },
        }
      }
      const operation = pending.current
      const turn = await chatRequest(
        `/conversations/${operation.conversation}/turns`,
        { method: 'POST', body: JSON.stringify(operation.body) },
      )
      if (turn.state === 'pending') {
        setRetry(true)
        setStatus('Reading is still running. Check the same request again.')
        return
      }
      pending.current = null
      setRetry(false)
      setStatus(turn.result.text ?? 'Photo request finished.')
      if (turn.result.proposal_id) setProposal(turn.result.proposal_id)
      if (turn.result.sources?.[0]) await openSource(turn.result.sources[0].id)
      setSelected(await request('photos/' + selected.id))
      await load()
    } catch (caught) {
      if (caught instanceof ChatRequestError && caught.status < 500) {
        pending.current = null
        setRetry(false)
      } else setRetry(!!pending.current)
      setError((caught as Error).message)
    } finally {
      setBusy(false)
    }
  }
  async function remove() {
    if (!selected || !deleteAcknowledged) return
    setBusy(true)
    setError('')
    try {
      await request('photos/delete', {
        method: 'POST',
        body: JSON.stringify({
          photo_id: selected.id,
          expected_updated_at: selected.updated_at,
        }),
      })
      setSelected(null)
      setSource(null)
      setProposal('')
      setDeleteAcknowledged(false)
      await load()
      setStatus(
        'Original and preview deleted. Derived text and earlier backups may remain.',
      )
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <section
      className="photos-panel"
      aria-label={assetId ? 'Photos and documents' : 'Private photos'}
    >
      <h2>{assetId ? 'Photos & Documents' : 'Private photos'}</h2>
      <p>
        Save receipt and nameplate photos. A general attachment alone supports
        no ownership claim.
      </p>
      <form onSubmit={(event) => void upload(event)} className="photo-upload">
        <label>
          Photo file
          <input
            ref={uploadInput}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            disabled={busy || retry}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <label>
          Photo purpose
          <select
            value={purpose}
            disabled={busy || retry}
            onChange={(e) => setPurpose(e.target.value)}
          >
            <option value="photo">General photo</option>
            <option value="receipt">Receipt</option>
            <option value="nameplate">Nameplate</option>
          </select>
        </label>
        <p>
          JPEG, PNG or WebP · 8 MiB · 20 megapixels. Original retained
          privately; preview has metadata removed.
        </p>
        <Button disabled={!file || busy || retry}>
          Upload privately{assetId ? ' to this item' : ''}
        </Button>
      </form>
      {error && <p role="alert">{error}</p>}
      {status && <p role="status">{status}</p>}
      {!items.length && <p>No photos saved here yet.</p>}
      <ul className="photo-grid">
        {items.map((row) => (
          <li key={row.id}>
            <button
              type="button"
              disabled={busy || retry}
              onClick={() => {
                setSelected(row)
                setProposal('')
                setSource(null)
                setDeleteAcknowledged(false)
                setStatus('')
              }}
            >
              <img
                loading="lazy"
                src={`/api/photos/${row.id}/preview`}
                alt=""
              />
              <span>{row.filename}</span>
              <small>{row.purpose}</small>
            </button>
          </li>
        ))}
      </ul>
      {cursor && (
        <Button
          disabled={busy}
          onClick={() =>
            void load(cursor).catch(() =>
              setError('Unable to load more photos.'),
            )
          }
        >
          More photos
        </Button>
      )}
      {selected && (
        <section className="photo-detail" aria-label="Photo details">
          <h3>{selected.filename}</h3>
          <img
            className="photo-preview"
            src={`/api/photos/${selected.id}/preview`}
            alt={`Preview of ${selected.filename}`}
          />
          <p>
            {selected.width} × {selected.height} ·{' '}
            {(selected.size / 1024).toFixed(1)} KiB original
          </p>
          <a href={`/api/photos/${selected.id}/original`} download>
            Download original
          </a>
          <details>
            <summary>Read photo with AI</summary>
            <p>
              Send only this metadata-free preview to your selected provider.
              The AI transcription is unverified: compare it with the original
              before confirming details. No asset is created until you review
              it.
            </p>
            {!consent && (
              <p>Enable external AI permission in Settings first.</p>
            )}
            <label>
              AI connection
              <select
                value={credential}
                disabled={busy || retry}
                onChange={(e) => {
                  setCredential(e.target.value)
                  setModel('')
                }}
              >
                <option value="">Choose connection</option>
                {credentials.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label} ·{' '}
                    {c.provider === 'anthropic' ? 'Claude' : 'OpenAI'}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Vision-capable model
              <input
                value={model}
                maxLength={100}
                disabled={busy || retry}
                onChange={(e) => setModel(e.target.value)}
                placeholder="Your provider model ID"
              />
            </label>
            <p>
              Uses the shared limit of 20 AI requests per day. A saved reading
              is reused.
            </p>
            <Button
              disabled={busy || (!retry && (!consent || !credential || !model))}
              onClick={() => void read()}
            >
              {retry
                ? 'Check same photo request'
                : busy
                  ? 'Reading…'
                  : 'Read this photo'}
            </Button>
          </details>
          {selected.source_id && (
            <Button
              disabled={busy}
              onClick={() => void openSource(selected.source_id!)}
            >
              View saved transcription
            </Button>
          )}
          <details>
            <summary>Delete this photo</summary>
            <p>
              Deletes this original and preview for every attached item. Derived
              text and facts remain; pending proposals cannot be accepted.
              Earlier backups may retain the image.
            </p>
            <label>
              <input
                type="checkbox"
                checked={deleteAcknowledged}
                disabled={busy || retry}
                onChange={(e) => setDeleteAcknowledged(e.target.checked)}
              />
              I understand what will be deleted and what remains.
            </label>
            <Button
              variant="outline"
              disabled={!deleteAcknowledged || busy || retry}
              onClick={() => void remove()}
            >
              Delete original and preview
            </Button>
          </details>
        </section>
      )}
      {source && (
        <EvidencePanel
          key={source.id}
          source={source}
          nextOffset={null}
          opening={busy}
          request={chatRequest}
          onOpen={openSource}
          onClose={() => setSource(null)}
          onViewProposal={setProposal}
        />
      )}
      {proposal && (
        <AssetProposalCard
          key={proposal}
          id={proposal}
          request={chatRequest}
          onOpen={openSource}
        />
      )}
    </section>
  )
}
