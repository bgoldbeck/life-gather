import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import './photos.css'
import { ChatPhotoUpload } from './ChatPhotoUpload'

export type SavedChatPhoto = { id: string; filename: string; purpose: string }

const PAGE = 12

type PhotoPage = { items: SavedChatPhoto[]; next_cursor: string | null }

async function fetchPhotos(
  cursor: string | null,
  signal: AbortSignal,
): Promise<PhotoPage> {
  const response = await fetch(
    `/api/photos?limit=${PAGE}${cursor ? '&cursor=' + encodeURIComponent(cursor) : ''}`,
    { credentials: 'same-origin', cache: 'no-store', signal },
  )
  if (!response.ok) throw new Error()
  return response.json()
}

/** Append a page, keeping the first copy of any photo already listed. */
function merge(old: SavedChatPhoto[], page: PhotoPage) {
  const rows = [...old]
  const known = new Set(rows.map((photo) => photo.id))
  for (const photo of page.items) {
    if (!known.has(photo.id)) {
      rows.push(photo)
      known.add(photo.id)
    }
  }
  return rows
}

export function ChatPhotoPicker({
  csrfToken,
  selected,
  onSelect,
  disabled,
  autoLoad = false,
}: {
  csrfToken: string
  selected: SavedChatPhoto | null
  onSelect: (photo: SavedChatPhoto | null) => void
  disabled: boolean
  /** Open the saved library straight away instead of waiting for a click. */
  autoLoad?: boolean
}) {
  const [items, setItems] = useState<SavedChatPhoto[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [busy, setBusy] = useState(autoLoad)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const controller = useRef<AbortController | null>(null)
  useEffect(() => () => controller.current?.abort(), [])
  useEffect(() => {
    // The first page loads once when the picker opens; later loads are explicit.
    if (!autoLoad) return
    const pending = new AbortController()
    controller.current = pending
    fetchPhotos(null, pending.signal)
      .then((page) => {
        if (pending.signal.aborted) return
        setItems((old) => merge(old, page))
        setCursor(page.next_cursor)
        if (!page.items.length)
          setMessage('No saved private photos. Upload one below or in Photos.')
      })
      .catch(() => {
        if (!pending.signal.aborted)
          setError('Unable to load saved photos. Try again.')
      })
      .finally(() => {
        if (!pending.signal.aborted) setBusy(false)
      })
    return () => pending.abort()
  }, [autoLoad])
  async function load(more = false) {
    controller.current?.abort()
    const pending = new AbortController()
    controller.current = pending
    setBusy(true)
    setError('')
    setMessage('')
    if (!more) onSelect(null)
    try {
      const page = await fetchPhotos(more ? cursor : null, pending.signal)
      if (pending.signal.aborted) return
      setItems((old) => merge(more ? old : [], page))
      setCursor(page.next_cursor)
      if (!more && !page.items.length)
        setMessage('No saved private photos. Upload one in Photos first.')
    } catch {
      if (!pending.signal.aborted)
        setError('Unable to load saved photos. Try again.')
    } finally {
      if (!pending.signal.aborted) setBusy(false)
    }
  }
  return (
    <section
      className="chat-photo-picker"
      aria-label="Choose a saved photo for Chat"
    >
      <h3>Choose a saved private photo</h3>
      <p>
        {autoLoad
          ? 'Pick one of your saved photos, or upload a new one below. Choosing makes no AI request.'
          : 'Load your private library, then select one original to read. Choosing a photo makes no AI request. You can also upload a new original below.'}
      </p>
      {(!autoLoad || error) && (
        <Button
          type="button"
          variant="outline"
          disabled={disabled || busy || uploadBusy}
          onClick={() => void load()}
        >
          Load saved Chat photos
        </Button>
      )}
      <ul className="photo-grid">
        {items.map((photo) => (
          <li key={photo.id}>
            <Button
              type="button"
              variant="outline"
              disabled={disabled || busy || uploadBusy}
              aria-pressed={selected?.id === photo.id}
              aria-label={`Choose photo ${photo.filename}`}
              onClick={() => onSelect(photo)}
            >
              <img
                loading="lazy"
                alt=""
                src={`/api/photos/${photo.id}/preview`}
              />
              <span title={photo.filename}>{photo.filename}</span>
              <small>{photo.purpose}</small>
            </Button>
          </li>
        ))}
      </ul>
      {cursor && (
        <Button
          type="button"
          variant="outline"
          disabled={disabled || busy || uploadBusy}
          onClick={() => void load(true)}
        >
          More saved Chat photos
        </Button>
      )}
      {selected && (
        <p>
          Selected photo: <strong>{selected.filename}</strong>.{' '}
          <Button
            type="button"
            variant="outline"
            disabled={disabled || busy || uploadBusy}
            onClick={() => onSelect(null)}
          >
            Clear Chat photo
          </Button>
        </p>
      )}
      {busy && <p role="status">Loading saved photo choices…</p>}
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
      <ChatPhotoUpload
        csrfToken={csrfToken}
        disabled={disabled || busy}
        onBusy={setUploadBusy}
        onStart={() => onSelect(null)}
        onSaved={(photo) => {
          setItems((old) => [
            photo,
            ...old.filter((row) => row.id !== photo.id),
          ])
          onSelect(photo)
          setError('')
          setMessage('')
        }}
      />
    </section>
  )
}
