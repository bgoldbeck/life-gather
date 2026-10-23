import { useEffect, useRef, useState } from 'react'
import { FileText, Image as ImageIcon, Share2, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { formatBytes } from './formatBytes'
import {
  type Kind,
  type ShareRequest,
  claimShareOnce,
  fileKind,
} from './shareTarget'
import './shared-files.css'

// Android's "Share to LifeGather" hands files to the service worker, which
// keeps them in memory until this screen claims them once. Each file is then
// saved through the ordinary Photos or Documents upload, so the session,
// size limit and storage quota apply exactly as for a manual upload.

type Status = 'ready' | 'saving' | 'saved' | 'failed'
type Item = {
  file: File
  kind: Kind
  purpose: string
  status: Status
  message: string
}

async function failure(response: Response): Promise<string> {
  if (response.status === 413) return 'This file is larger than 8 MiB.'
  if (response.status === 401 || response.status === 403)
    return 'Your session ended. Sign in again, then share the file again.'
  try {
    const detail = ((await response.json()) as { detail?: unknown }).detail
    if (typeof detail === 'string' && detail) return detail
  } catch {
    // The server sent no readable reason.
  }
  return 'LifeGather did not accept this file. Check it and try again.'
}

export function SharedFiles({
  share,
  csrfToken,
  refreshSession,
  onClose,
  onOpenPhotos,
  onOpenDocuments,
  claim = claimShareOnce,
}: {
  share: ShareRequest
  csrfToken: string
  refreshSession?: () => Promise<void>
  onClose: () => void
  onOpenPhotos: () => void
  onOpenDocuments: () => void
  claim?: (id: string) => Promise<File[]>
}) {
  const [claimed, setItems] = useState<Item[] | null>(null)
  const [busy, setBusy] = useState(false)
  const active = useRef(true)
  const claimedId = useRef('')
  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
    }
  }, [])
  // "unavailable" and "empty" come from the server or worker with no files.
  const claimable = /^[0-9a-f]{32}$/.test(share.id)
  useEffect(() => {
    if (!claimable) return
    // Claim once: the worker forgets the files as soon as it hands them over.
    if (claimedId.current === share.id) return
    claimedId.current = share.id
    claim(share.id)
      .catch(() => [] as File[])
      .then((files) => {
        if (!active.current) return
        setItems(
          files.map((file) => ({
            file,
            kind: fileKind(file),
            purpose: 'photo',
            status: 'ready',
            message: '',
          })),
        )
      })
  }, [share.id, claimable, claim])

  const items = claimable ? claimed : []
  const update = (index: number, change: Partial<Item>) =>
    setItems(
      (current) =>
        current?.map((item, position) =>
          position === index ? { ...item, ...change } : item,
        ) ?? current,
    )

  async function save(item: Item): Promise<Partial<Item>> {
    const path =
      item.kind === 'photo'
        ? `/api/photos?purpose=${encodeURIComponent(item.purpose)}`
        : '/api/documents?encoding=utf-8-sig'
    try {
      const response = await fetch(path, {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'Content-Type':
            item.kind === 'photo'
              ? 'application/octet-stream'
              : item.file.type || 'application/octet-stream',
          'X-CSRF-Token': csrfToken,
          'X-File-Name': encodeURIComponent(item.file.name),
        },
        body: item.file,
      })
      if (response.status === 401) await refreshSession?.()
      if (response.ok) return { status: 'saved', message: '' }
      return { status: 'failed', message: await failure(response) }
    } catch {
      return {
        status: 'failed',
        message:
          'The upload outcome is unknown. Check Photos or Documents before trying again.',
      }
    }
  }

  async function saveAll() {
    if (!items || busy) return
    setBusy(true)
    for (const [index, item] of items.entries()) {
      if (!active.current) return
      if (
        (item.kind !== 'photo' && item.kind !== 'document') ||
        item.status === 'saved'
      )
        continue
      update(index, { status: 'saving', message: '' })
      const result = await save(item)
      if (!active.current) return
      update(index, result)
    }
    setBusy(false)
  }

  const savable = (items ?? []).filter(
    (item) =>
      (item.kind === 'photo' || item.kind === 'document') &&
      item.status !== 'saved',
  )
  const savedPhotos = (items ?? []).some(
    (item) => item.kind === 'photo' && item.status === 'saved',
  )
  const savedDocuments = (items ?? []).some(
    (item) => item.kind === 'document' && item.status === 'saved',
  )

  return (
    <section className="shared-files" aria-labelledby="shared-files-title">
      <header>
        <Share2 aria-hidden="true" size={20} />
        <h2 id="shared-files-title">Shared to LifeGather</h2>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Close shared files"
          onClick={onClose}
          disabled={busy}
        >
          <X aria-hidden="true" size={16} />
        </Button>
      </header>
      {items === null ? (
        <p role="status">Opening the shared files…</p>
      ) : !items.length ? (
        <p role="status">
          {share.id === 'empty'
            ? 'Nothing was shared. Choose a photo or document, then share it to LifeGather.'
            : 'The shared files are no longer available. Shared files are kept on this phone only until LifeGather opens, and are never stored there. Open LifeGather once, then share the files again.'}
        </p>
      ) : (
        <>
          <p>
            Review what you shared, then save it to your private library. Saving
            uses your normal storage and makes no AI request.
          </p>
          {share.more && (
            <p role="note">Only the first 10 files were received.</p>
          )}
          <ul>
            {items.map((item, index) => (
              <li key={index} data-status={item.status}>
                {item.kind === 'photo' ? (
                  <ImageIcon aria-hidden="true" size={18} />
                ) : (
                  <FileText aria-hidden="true" size={18} />
                )}
                <div className="shared-file-name">
                  <strong>{item.file.name || 'Shared file'}</strong>
                  <small>
                    {formatBytes(item.file.size)}
                    {' · '}
                    {item.kind === 'photo'
                      ? 'Photo'
                      : item.kind === 'document'
                        ? 'Document'
                        : item.kind === 'too-large'
                          ? 'Larger than 8 MiB, cannot be saved'
                          : 'This file type cannot be saved'}
                  </small>
                </div>
                {item.kind === 'photo' && item.status !== 'saved' && (
                  <label>
                    <span className="sr-only">
                      Photo purpose for {item.file.name || 'shared file'}
                    </span>
                    <select
                      value={item.purpose}
                      disabled={busy}
                      onChange={(event) =>
                        update(index, { purpose: event.target.value })
                      }
                    >
                      <option value="photo">Photo</option>
                      <option value="receipt">Receipt</option>
                      <option value="nameplate">Nameplate</option>
                    </select>
                  </label>
                )}
                <span className="shared-file-status" role="status">
                  {item.status === 'saving'
                    ? 'Saving…'
                    : item.status === 'saved'
                      ? 'Saved'
                      : item.message}
                </span>
              </li>
            ))}
          </ul>
          <div className="shared-files-actions">
            {savable.length > 0 && (
              <Button onClick={saveAll} disabled={busy}>
                {busy
                  ? 'Saving…'
                  : savable.length === 1
                    ? 'Save 1 file'
                    : `Save ${savable.length} files`}
              </Button>
            )}
            {savedPhotos && (
              <Button variant="outline" onClick={onOpenPhotos}>
                Open Photos
              </Button>
            )}
            {savedDocuments && (
              <Button variant="outline" onClick={onOpenDocuments}>
                Open Documents
              </Button>
            )}
            <Button variant="ghost" onClick={onClose} disabled={busy}>
              {savable.length ? 'Discard' : 'Done'}
            </Button>
          </div>
        </>
      )}
    </section>
  )
}
