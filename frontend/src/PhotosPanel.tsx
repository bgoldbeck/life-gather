import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { BulkDelete } from './BulkDelete'
import { PhotoAssetLinks } from './PhotoAssetLinks'
import { isAIProvider, aiProviderLabel } from './aiProviders'
import { AssetProposalCard } from './AssetProposalCard'
import { ReceiptProposalCard } from './ReceiptProposalCard'
import { EvidencePanel, type EvidenceSource } from './EvidencePanel'
import { ChatRequestError } from './chatRequest'
import { ExistingPhotoLink } from './ExistingPhotoLink'
import { UndoNotice, type UndoAction } from './UndoNotice'
import {
  CameraCaptureButton,
  CANCELLED_MESSAGE,
  PhotoUploadProgress,
} from './PhotoCapture'
import { PHOTO_ACCEPT, photoFileProblem, sendPhoto } from './photoUpload'
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
  initialPhotoId = '',
  onOpenAsset,
}: {
  csrfToken: string
  assetId?: string
  initialPhotoId?: string
  onOpenAsset?: (id: string) => void
}) {
  const [items, setItems] = useState<Photo[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [selected, setSelected] = useState<Photo | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [purpose, setPurpose] = useState('photo')
  const [busy, setBusy] = useState(false)
  const [linking, setLinking] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [undo, setUndo] = useState<UndoAction | null>(null)
  const [credentials, setCredentials] = useState<Credential[]>([])
  const [credential, setCredential] = useState('')
  const [model, setModel] = useState('')
  const [consent, setConsent] = useState(false)
  const [proposal, setProposal] = useState('')
  const [receipt, setReceipt] = useState('')
  const [source, setSource] = useState<EvidenceSource | null>(null)
  const [sourceOpening, setSourceOpening] = useState(false)
  const sourceGeneration = useRef(0)
  const listGeneration = useRef(0)
  const [deleteAcknowledged, setDeleteAcknowledged] = useState(false)
  const [retry, setRetry] = useState(false)
  const pending = useRef<Pending | null>(null)
  const uploadInput = useRef<HTMLInputElement>(null)
  const uploadController = useRef<AbortController | null>(null)
  const [percent, setPercent] = useState(0)
  const [uploading, setUploading] = useState(false)
  const [uploadUncertain, setUploadUncertain] = useState(false)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      uploadController.current?.abort()
    }
  }, [])
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
      const generation = ++listGeneration.current
      try {
        const page = await request(
          `photos?asset_id=${encodeURIComponent(assetId)}&cursor=${next}`,
        )
        if (generation !== listGeneration.current) return
        setItems((current) => (next ? [...current, ...page.items] : page.items))
        setCursor(page.next_cursor)
      } catch (caught) {
        if (generation === listGeneration.current) throw caught
      }
    },
    [request, assetId],
  )
  useEffect(() => {
    let alive = true
    const generation = ++listGeneration.current
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
        if (generation === listGeneration.current) {
          setItems(page.items)
          setCursor(page.next_cursor)
        }
        setCredentials(
          (entries.items ?? []).filter(
            (c: Credential) => c.kind === 'ai' && isAIProvider(c.provider),
          ),
        )
        setConsent(settings.allow_external_ai === true)
      })
      .catch(() => {
        if (alive && generation === listGeneration.current)
          setError('Unable to load photos. Reopen this view to retry.')
      })
    return () => {
      alive = false
      controller.abort()
    }
  }, [request, assetId])

  useEffect(() => {
    if (!initialPhotoId) return
    const controller = new AbortController()
    void request('photos/' + encodeURIComponent(initialPhotoId), {
      signal: controller.signal,
    })
      .then((row: Photo) => {
        if (!controller.signal.aborted) setSelected(row)
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError('Unable to open that photo. It may have been deleted.')
      })
    return () => controller.abort()
  }, [request, initialPhotoId])

  const invalidateReads = useCallback(() => {
    ++listGeneration.current
    ++sourceGeneration.current
  }, [])
  useEffect(() => invalidateReads, [invalidateReads])

  async function upload(chosen = file) {
    if (!chosen || busy || retry || linking) return
    const problem = photoFileProblem(chosen)
    if (problem) {
      setError(problem)
      setStatus('')
      return
    }
    const controller = new AbortController()
    uploadController.current = controller
    setBusy(true)
    setUploading(true)
    setPercent(0)
    setError('')
    setStatus('')
    const result = await sendPhoto<Photo>({
      url: `/api/photos?purpose=${purpose}&asset_id=${encodeURIComponent(assetId)}`,
      file: chosen,
      csrfToken,
      signal: controller.signal,
      onProgress: (value) => mounted.current && setPercent(value),
    })
    if (!mounted.current) return
    uploadController.current = null
    setUploading(false)
    try {
      if (result.kind === 'saved') {
        setUploadUncertain(false)
        setSelected(result.photo)
        setDeleteAcknowledged(false)
        setProposal('')
        setReceipt('')
        clearSource()
        setFile(null)
        if (uploadInput.current) uploadInput.current.value = ''
        setStatus('Photo saved privately. No AI request was made.')
        await load()
      } else if (result.kind === 'cancelled') setStatus(CANCELLED_MESSAGE)
      else if (result.kind === 'rejected') {
        setUploadUncertain(false)
        setError(
          'Photo was not accepted. Check the file, storage limit and session, then try again.',
        )
      } else {
        setUploadUncertain(true)
        setError(
          'Upload outcome is unknown. Retry the same photo safely; it is never saved twice.',
        )
      }
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setBusy(false)
    }
  }
  function clearSource() {
    ++sourceGeneration.current
    setSource(null)
    setSourceOpening(false)
  }
  async function openSource(id: string) {
    const generation = ++sourceGeneration.current
    setSourceOpening(true)
    setError('')
    try {
      const evidence = await chatRequest('/sources/' + id)
      if (generation === sourceGeneration.current) setSource(evidence)
    } catch (caught) {
      if (generation === sourceGeneration.current)
        setError((caught as Error).message)
    } finally {
      if (generation === sourceGeneration.current) setSourceOpening(false)
    }
  }
  async function read() {
    if (!selected || busy || linking) return
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
      setProposal(turn.result.proposal_id ?? '')
      setReceipt(turn.result.receipt_proposal_id ?? '')
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
  async function detach() {
    if (!selected || !assetId || busy || retry || linking) return
    setBusy(true)
    setError('')
    setStatus('')
    try {
      const detached: Photo = await request('photos/detach', {
        method: 'POST',
        body: JSON.stringify({
          photo_id: selected.id,
          asset_id: assetId,
          expected_updated_at: selected.updated_at,
        }),
      })
      setSelected(null)
      clearSource()
      setProposal('')
      setReceipt('')
      await load()
      const message =
        'Photo removed from this item. The original, other galleries and source evidence remain available.'
      setStatus(message)
      setUndo({
        message,
        label: 'Undo photo removal',
        run: async () => {
          try {
            await request('photos/attach', {
              method: 'POST',
              body: JSON.stringify({
                photo_id: detached.id,
                asset_id: assetId,
                expected_updated_at: detached.updated_at,
              }),
            })
          } catch {
            throw new Error(
              'Unable to attach the photo again. It may have changed or been deleted; use a photo already saved instead.',
            )
          }
          await load()
          return 'Photo attached to this item again.'
        },
      })
    } catch {
      setError(
        'Unable to remove the link. Retry, or reopen this gallery if the photo changed.',
      )
    } finally {
      setBusy(false)
    }
  }
  async function remove() {
    if (!selected || !deleteAcknowledged || busy || retry || linking) return
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
      clearSource()
      setProposal('')
      setReceipt('')
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
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void upload()
        }}
        className="photo-upload"
      >
        <label>
          Photo file
          <input
            ref={uploadInput}
            type="file"
            accept={PHOTO_ACCEPT}
            disabled={busy || retry || linking || uploadUncertain}
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null)
              setError('')
              setStatus('')
            }}
          />
        </label>
        <label>
          Photo purpose
          <select
            value={purpose}
            disabled={busy || retry || linking || uploadUncertain}
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
        <div className="photo-upload-actions">
          <CameraCaptureButton
            label={'Take a photo' + (assetId ? ' of this item' : '')}
            disabled={busy || retry || linking || uploadUncertain}
            onCapture={(captured) => {
              setFile(captured)
              void upload(captured)
            }}
          />
          <Button
            variant={uploadUncertain ? 'default' : 'outline'}
            disabled={!file || busy || retry || linking}
          >
            {uploadUncertain
              ? 'Retry same photo upload'
              : 'Upload privately' + (assetId ? ' to this item' : '')}
          </Button>
        </div>
        {file && !busy && !uploadUncertain && (
          <p>Photo ready to upload: {file.name}</p>
        )}
        {uploading && (
          <PhotoUploadProgress
            percent={percent}
            onCancel={() => uploadController.current?.abort()}
          />
        )}
      </form>
      {assetId && (
        <details>
          <summary>Use a photo already saved</summary>
          <ExistingPhotoLink
            assetId={assetId}
            csrfToken={csrfToken}
            disabled={busy || retry}
            onLinked={async () => {
              setError('')
              setStatus('')
              await load()
            }}
            onLockedChange={setLinking}
          />
        </details>
      )}
      {error && <p role="alert">{error}</p>}
      {undo && undo.message === status ? (
        <UndoNotice
          action={undo}
          disabled={busy || retry || linking}
          onBusy={setBusy}
          onDone={(message) => {
            setUndo(null)
            setStatus(message)
          }}
        />
      ) : (
        status && <p role="status">{status}</p>
      )}
      {!items.length && (
        <p className="empty-state">No photos saved here yet.</p>
      )}
      <ul className="photo-grid">
        {items.map((row) => (
          <li key={row.id}>
            <button
              type="button"
              disabled={busy || retry || linking}
              onClick={() => {
                setSelected(row)
                setProposal('')
                setReceipt('')
                clearSource()
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
          disabled={busy || retry || linking}
          onClick={() =>
            void load(cursor).catch(() =>
              setError('Unable to load more photos.'),
            )
          }
        >
          More photos
        </Button>
      )}
      <BulkDelete
        kind="photos"
        items={items.map((row) => ({
          id: row.id,
          label: row.filename,
          updated_at: row.updated_at,
        }))}
        request={request}
        disabled={busy || retry || linking}
        onDeleted={async (ids) => {
          if (selected && ids.includes(selected.id)) {
            setSelected(null)
            clearSource()
            setProposal('')
            setReceipt('')
            setDeleteAcknowledged(false)
          }
          await load()
        }}
      />
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
                disabled={busy || retry || linking}
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
              Vision-capable model
              <input
                value={model}
                maxLength={100}
                disabled={busy || retry || linking}
                onChange={(e) => setModel(e.target.value)}
                placeholder="Your provider model ID"
              />
            </label>
            <p>
              Uses the shared limit of 20 AI requests per day. A saved reading
              is reused.
            </p>
            <Button
              disabled={
                busy ||
                linking ||
                (!retry && (!consent || !credential || !model))
              }
              onClick={() => void read()}
            >
              {retry
                ? 'Check same photo request'
                : busy
                  ? 'Reading…'
                  : 'Read this photo'}
            </Button>
          </details>
          {onOpenAsset && (
            <PhotoAssetLinks
              key={`${selected.id}:${selected.updated_at}`}
              photoId={selected.id}
              revision={selected.updated_at}
              onOpenAsset={onOpenAsset}
            />
          )}
          {selected.source_id && (
            <Button
              disabled={busy || retry || linking || sourceOpening}
              onClick={() => void openSource(selected.source_id!)}
            >
              View saved transcription
            </Button>
          )}
          {assetId && (
            <section aria-label="Remove gallery attachment">
              <p>
                Remove this gallery attachment while keeping the original, other
                item attachments and any source evidence. You can attach it
                again by choosing the saved photo or uploading the same file to
                this item.
              </p>
              <Button
                variant="outline"
                disabled={busy || retry || linking}
                onClick={() => void detach()}
              >
                Remove photo from this item
              </Button>
            </section>
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
                disabled={busy || retry || linking}
                onChange={(e) => setDeleteAcknowledged(e.target.checked)}
              />
              I understand what will be deleted and what remains.
            </label>
            <Button
              variant="outline"
              disabled={!deleteAcknowledged || busy || retry || linking}
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
          opening={busy || sourceOpening}
          request={chatRequest}
          onOpen={openSource}
          onClose={clearSource}
          onViewProposal={setProposal}
        />
      )}
      {receipt && (
        <ReceiptProposalCard
          id={receipt}
          csrfToken={csrfToken}
          onOpen={openSource}
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
