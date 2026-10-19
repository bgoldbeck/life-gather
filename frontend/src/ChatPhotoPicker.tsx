import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import './photos.css'

export type SavedChatPhoto = { id: string; filename: string; purpose: string }

export function ChatPhotoPicker({
  selected,
  onSelect,
  disabled,
}: {
  selected: SavedChatPhoto | null
  onSelect: (photo: SavedChatPhoto | null) => void
  disabled: boolean
}) {
  const [items, setItems] = useState<SavedChatPhoto[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
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
      setItems((old) => [...(more ? old : []), ...page.items])
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
        photo makes no AI request. Upload new images in Photos.
      </p>
      <Button
        type="button"
        variant="outline"
        disabled={disabled || busy}
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
              disabled={disabled || busy}
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
          disabled={disabled || busy}
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
            disabled={disabled || busy}
            onClick={() => onSelect(null)}
          >
            Clear Chat photo
          </Button>
        </p>
      )}
      {busy && <p role="status">Loading saved photo choices…</p>}
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  )
}
