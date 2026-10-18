import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'

type Photo = {
  id: string
  filename: string
  purpose: string
  updated_at: number
}

export function ExistingPhotoLink({
  assetId,
  csrfToken,
  disabled,
  onLinked,
  onLockedChange,
}: {
  assetId: string
  csrfToken: string
  disabled: boolean
  onLinked: () => Promise<void>
  onLockedChange: (locked: boolean) => void
}) {
  const [items, setItems] = useState<Photo[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [selected, setSelected] = useState<Photo | null>(null)
  const [busy, setBusy] = useState(false)
  const [retry, setRetry] = useState(false)
  const [saved, setSaved] = useState(false)
  const [message, setMessage] = useState('')
  const pending = useRef<object | null>(null)
  const frozen = disabled || busy || retry || saved
  useEffect(() => {
    onLockedChange(busy || retry)
    return () => onLockedChange(false)
  }, [busy, retry, onLockedChange])
  async function load(more = false) {
    setBusy(true)
    setMessage('')
    if (!more) setSelected(null)
    try {
      const response = await fetch(
        `/api/photos?limit=5${more ? '&cursor=' + cursor : ''}`,
        { credentials: 'same-origin', cache: 'no-store' },
      )
      if (!response.ok) throw new Error()
      const page = await response.json()
      setItems((old) => [...(more ? old : []), ...page.items])
      setCursor(page.next_cursor)
      if (!page.items.length && !more)
        setMessage('No existing private photos are available.')
    } catch {
      setMessage('Unable to load saved photos. Try again.')
    } finally {
      setBusy(false)
    }
  }
  async function reload() {
    setBusy(true)
    try {
      await onLinked()
      setSaved(false)
      setSelected(null)
      setMessage(
        'Photo linked to this item. The original and other galleries remain available. No AI request was made.',
      )
    } catch {
      setMessage(
        'Photo link saved. Reload this gallery to see it; do not submit another link.',
      )
    } finally {
      setBusy(false)
    }
  }
  async function save() {
    if (busy || disabled || saved || (!pending.current && !selected)) return
    const body = pending.current ?? {
      photo_id: selected!.id,
      asset_id: assetId,
      expected_updated_at: selected!.updated_at,
    }
    pending.current = body
    setBusy(true)
    setMessage('')
    let complete = false
    try {
      const response = await fetch('/api/photos/attach', {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify(body),
      })
      if (!response.ok) {
        if (response.status < 500) {
          pending.current = null
          setRetry(false)
          setSelected(null)
          setMessage(
            'Photo link refused. Reload saved photos and select the current photo again.',
          )
          return
        }
        throw new Error()
      }
      const photo: Photo = await response.json()
      setItems((old) =>
        old.map((item) => (item.id === photo.id ? photo : item)),
      )
      pending.current = null
      setRetry(false)
      setSaved(true)
      complete = true
    } catch {
      setRetry(true)
      setMessage('Connection lost. Retry the same photo link safely.')
    } finally {
      setBusy(false)
    }
    if (complete) await reload()
  }
  return (
    <section aria-label="Link an existing private photo">
      <h3>Link an existing private photo</h3>
      <p>
        Choose a photo already in your private library. This adds a gallery link
        without uploading or copying the original. A general attachment supports
        no ownership claim.
      </p>
      <Button variant="outline" disabled={frozen} onClick={() => void load()}>
        Load saved photos
      </Button>
      <ul className="photo-grid">
        {items.map((photo) => (
          <li key={photo.id}>
            <button
              type="button"
              disabled={frozen}
              aria-pressed={selected?.id === photo.id}
              onClick={() => setSelected(photo)}
            >
              <img
                loading="lazy"
                src={`/api/photos/${photo.id}/preview`}
                alt=""
              />
              <span>{photo.filename}</span>
              <small>
                {photo.purpose} · {photo.id.slice(0, 8)}
              </small>
            </button>
          </li>
        ))}
      </ul>
      {cursor && (
        <Button
          variant="outline"
          disabled={frozen}
          onClick={() => void load(true)}
        >
          More saved photos
        </Button>
      )}
      {selected && (
        <p>
          Selected photo: {selected.filename} · {selected.id.slice(0, 8)}. Other
          gallery links will remain.
        </p>
      )}
      {message && <p role="status">{message}</p>}
      <Button
        disabled={disabled || busy || saved || (!retry && !selected)}
        onClick={() => void save()}
      >
        {retry ? 'Retry same photo link' : 'Link selected photo to this item'}
      </Button>
      {saved && (
        <Button
          variant="outline"
          disabled={disabled || busy}
          onClick={() => void reload()}
        >
          Reload linked gallery
        </Button>
      )}
    </section>
  )
}
