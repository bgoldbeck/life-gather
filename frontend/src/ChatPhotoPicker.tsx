import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import './photos.css'
import { ChatPhotoUpload } from './ChatPhotoUpload'

export type SavedChatPhoto = { id: string; filename: string; purpose: string }

export function ChatPhotoPicker({
  csrfToken,
  selected,
  onSelect,
  disabled,
}: {
  csrfToken: string
  selected: SavedChatPhoto | null
  onSelect: (photo: SavedChatPhoto | null) => void
  disabled: boolean
}) {
  const [items, setItems] = useState<SavedChatPhoto[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const controller = useRef<AbortController | null>(null)
  useEffect(() => () => controller.current?.abort(), [])
  async function load(more = false) {
    controller.current?.abort()
    const pending = new AbortController()
    controller.current = pending
    setBusy(true)
    setError('')
    setMessage('')
    if (!more) onSelect(null)
    try {
      const response = await fetch(
        `/api/photos?limit=5${more ? '&cursor=' + encodeURIComponent(cursor ?? '') : ''}`,
        {
          credentials: 'same-origin',
          cache: 'no-store',
          signal: pending.signal,
        },
      )
      if (!response.ok) throw new Error()
      const page = await response.json()
      if (pending.signal.aborted) return
      setItems((old) => {
        const rows: SavedChatPhoto[] = more ? [...old] : []
        const known = new Set(rows.map((photo) => photo.id))
        for (const photo of page.items) {
          if (!known.has(photo.id)) {
            rows.push(photo)
            known.add(photo.id)
          }
        }
        return rows
      })
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
        Load your private library, then select one original to read. Choosing a
        photo makes no AI request. You can also upload a new original below.
      </p>
      <Button
        type="button"
        variant="outline"
        disabled={disabled || busy || uploadBusy}
        onClick={() => void load()}
      >
        Load saved Chat photos
      </Button>
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
              <span>{photo.filename}</span>
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
