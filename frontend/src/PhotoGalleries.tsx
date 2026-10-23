import { useCallback, useEffect, useState } from 'react'
import { Images, Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  allPhotos,
  galleryDate,
  MAX_ADD,
  photoCount,
  type Gallery,
  type GalleryRequest as Request,
  type SavedPhoto,
} from './photoGalleries'

function GalleryFields({
  title,
  eventOn,
  disabled,
  onTitle,
  onEventOn,
}: {
  title: string
  eventOn: string
  disabled: boolean
  onTitle: (value: string) => void
  onEventOn: (value: string) => void
}) {
  return (
    <div className="gallery-fields">
      <label>
        Gallery name
        <input
          value={title}
          maxLength={80}
          required
          disabled={disabled}
          placeholder="For example, Moving day"
          onChange={(event) => onTitle(event.target.value)}
        />
      </label>
      <label>
        Event date (optional)
        <input
          type="date"
          value={eventOn}
          disabled={disabled}
          onChange={(event) => onEventOn(event.target.value)}
        />
      </label>
    </div>
  )
}

export function GalleryBar({
  galleries,
  activeId,
  request,
  disabled,
  onSelect,
  onChanged,
}: {
  galleries: Gallery[]
  activeId: string
  request: Request
  disabled: boolean
  onSelect: (id: string) => void
  onChanged: () => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [eventOn, setEventOn] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function create() {
    if (busy || !title.trim()) return
    setBusy(true)
    setError('')
    try {
      const gallery: Gallery = await request('photo-galleries', {
        method: 'POST',
        body: JSON.stringify({ title, event_on: eventOn || null }),
      })
      setTitle('')
      setEventOn('')
      setOpen(false)
      await onChanged()
      onSelect(gallery.id)
    } catch {
      setError(
        'Unable to create the gallery. Its name may already be used; choose another.',
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="gallery-bar" aria-label="Galleries">
      <div className="gallery-bar-heading">
        <h3>
          <Images aria-hidden="true" size={18} />
          Galleries
        </h3>
        <Button
          variant="outline"
          size="sm"
          aria-expanded={open}
          disabled={disabled}
          onClick={() => setOpen((value) => !value)}
        >
          <Plus aria-hidden="true" size={14} />
          New gallery
        </Button>
      </div>
      <p>
        Group photos by event. A gallery only groups photos; it records no
        ownership or other facts.
      </p>
      <ul className="gallery-chips">
        <li>
          <button
            type="button"
            aria-pressed={!activeId}
            disabled={disabled}
            onClick={() => onSelect('')}
          >
            <strong>All photos</strong>
          </button>
        </li>
        {galleries.map((gallery) => (
          <li key={gallery.id}>
            <button
              type="button"
              aria-pressed={activeId === gallery.id}
              disabled={disabled}
              onClick={() => onSelect(gallery.id)}
            >
              {gallery.cover_photo_id ? (
                <img
                  loading="lazy"
                  src={`/api/photos/${gallery.cover_photo_id}/preview`}
                  alt=""
                />
              ) : (
                <span className="gallery-cover-empty" aria-hidden="true">
                  <Images size={16} />
                </span>
              )}
              <span>
                <strong>{gallery.title}</strong>
                <small>
                  {[
                    galleryDate(gallery.event_on),
                    photoCount(gallery.photo_count),
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </small>
              </span>
            </button>
          </li>
        ))}
      </ul>
      {open && (
        <form
          className="gallery-form"
          aria-label="New gallery"
          onSubmit={(event) => {
            event.preventDefault()
            void create()
          }}
        >
          <GalleryFields
            title={title}
            eventOn={eventOn}
            disabled={busy}
            onTitle={setTitle}
            onEventOn={setEventOn}
          />
          <Button disabled={busy || !title.trim()}>
            {busy ? 'Creating…' : 'Create gallery'}
          </Button>
        </form>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  )
}

export function GalleryHeader({
  gallery,
  request,
  disabled,
  onChanged,
  onDeleted,
}: {
  gallery: Gallery
  request: Request
  disabled: boolean
  onChanged: () => Promise<void>
  onDeleted: () => Promise<void>
}) {
  const [title, setTitle] = useState(gallery.title)
  const [eventOn, setEventOn] = useState(gallery.event_on ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [candidates, setCandidates] = useState<SavedPhoto[] | null>(null)
  const [chosen, setChosen] = useState<string[]>([])
  const frozen = disabled || busy
  const path = `photo-galleries/${encodeURIComponent(gallery.id)}`
  async function run(action: () => Promise<void>, failure: string) {
    setBusy(true)
    setError('')
    setStatus('')
    try {
      await action()
    } catch {
      setError(failure)
    } finally {
      setBusy(false)
    }
  }
  const save = () =>
    run(async () => {
      await request(path + '/update', {
        method: 'POST',
        body: JSON.stringify({
          title,
          event_on: eventOn || null,
          expected_updated_at: gallery.updated_at,
        }),
      })
      await onChanged()
      setStatus('Gallery saved.')
    }, 'Unable to save. The name may be used already, or the gallery changed; reload and retry.')
  const remove = () =>
    run(async () => {
      await request(path + '/delete', {
        method: 'POST',
        body: JSON.stringify({ expected_updated_at: gallery.updated_at }),
      })
      await onDeleted()
    }, 'Unable to delete the gallery. Reload it and retry.')
  const loadCandidates = () =>
    run(async () => {
      const [every, inside] = await Promise.all([
        allPhotos(request),
        allPhotos(request, gallery.id),
      ])
      const present = new Set(inside.map((photo) => photo.id))
      setCandidates(every.filter((photo) => !present.has(photo.id)))
      setChosen([])
    }, 'Unable to load saved photos. Try again.')
  const add = () =>
    run(async () => {
      const result = await request(path + '/photos', {
        method: 'POST',
        body: JSON.stringify({ photo_ids: chosen }),
      })
      setCandidates(null)
      setChosen([])
      await onChanged()
      setStatus(
        `${photoCount(result.added_count)} added to ${gallery.title}. No AI request was made.`,
      )
    }, 'Unable to add the photos. A photo may have been deleted; reload and retry.')
  const date = galleryDate(gallery.event_on)
  return (
    <section className="gallery-header" aria-label={`Gallery ${gallery.title}`}>
      <h3>{gallery.title}</h3>
      <p>
        {[date || 'No event date', photoCount(gallery.photo_count)].join(' · ')}
      </p>
      <div className="photo-upload-actions">
        <Button
          variant="outline"
          disabled={frozen}
          onClick={() =>
            void (candidates ? setCandidates(null) : loadCandidates())
          }
        >
          {candidates ? (
            <X aria-hidden="true" size={14} />
          ) : (
            <Plus aria-hidden="true" size={14} />
          )}
          {candidates ? 'Close photo picker' : 'Add photos'}
        </Button>
      </div>
      {candidates && (
        <fieldset className="gallery-picker" disabled={frozen}>
          <legend>Choose saved photos to add (up to {MAX_ADD})</legend>
          {candidates.length ? (
            <ul className="photo-grid">
              {candidates.map((photo) => {
                const on = chosen.includes(photo.id)
                return (
                  <li key={photo.id}>
                    <label className="gallery-pick">
                      <input
                        type="checkbox"
                        checked={on}
                        disabled={!on && chosen.length >= MAX_ADD}
                        onChange={(event) =>
                          setChosen((current) =>
                            event.target.checked
                              ? [...current, photo.id]
                              : current.filter((id) => id !== photo.id),
                          )
                        }
                      />
                      <img
                        loading="lazy"
                        src={`/api/photos/${photo.id}/preview`}
                        alt=""
                      />
                      <span>{photo.filename}</span>
                    </label>
                  </li>
                )
              })}
            </ul>
          ) : (
            <p className="empty-state">
              Every saved photo is already in this gallery.
            </p>
          )}
          <Button disabled={!chosen.length} onClick={() => void add()}>
            {chosen.length
              ? `Add ${photoCount(chosen.length)} to gallery`
              : 'Add to gallery'}
          </Button>
        </fieldset>
      )}
      <details>
        <summary>Edit gallery</summary>
        <form
          className="gallery-form"
          onSubmit={(event) => {
            event.preventDefault()
            void save()
          }}
        >
          <GalleryFields
            title={title}
            eventOn={eventOn}
            disabled={frozen}
            onTitle={setTitle}
            onEventOn={setEventOn}
          />
          <Button disabled={frozen || !title.trim()}>Save gallery</Button>
        </form>
      </details>
      <details>
        <summary>Delete gallery</summary>
        <p>
          Deletes only this gallery. Every photo in it stays saved, in All
          photos and in any other gallery.
        </p>
        <Button
          variant="outline"
          disabled={frozen}
          onClick={() => void remove()}
        >
          Delete gallery, keep photos
        </Button>
      </details>
      {error && <p role="alert">{error}</p>}
      {status && <p role="status">{status}</p>}
    </section>
  )
}

export function PhotoGalleryLinks({
  photoId,
  galleries,
  request,
  disabled,
  onChanged,
}: {
  photoId: string
  galleries: Gallery[]
  request: Request
  disabled: boolean
  onChanged: () => Promise<void>
}) {
  const [items, setItems] = useState<Gallery[] | null>(null)
  const [choice, setChoice] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const load = useCallback(
    () =>
      request(`photos/${encodeURIComponent(photoId)}/galleries`).then(
        (page: { items?: Gallery[] }) => page.items ?? [],
      ),
    [request, photoId],
  )
  useEffect(() => {
    let alive = true
    load()
      .then((found) => {
        if (alive) setItems(found)
      })
      .catch(() => {
        if (alive) setError('Unable to load the galleries this photo is in.')
      })
    return () => {
      alive = false
    }
  }, [load])
  async function change(galleryId: string, adding: boolean) {
    setBusy(true)
    setError('')
    try {
      const path = `photo-galleries/${encodeURIComponent(galleryId)}/photos`
      await request(adding ? path : path + '/remove', {
        method: 'POST',
        body: JSON.stringify(
          adding ? { photo_ids: [photoId] } : { photo_id: photoId },
        ),
      })
      setChoice('')
      setItems(await load())
      await onChanged()
    } catch {
      setError('Unable to change this photo’s galleries. Reload and retry.')
    } finally {
      setBusy(false)
    }
  }
  if (!items) return error ? <p role="alert">{error}</p> : null
  const held = new Set(items.map((gallery) => gallery.id))
  const others = galleries.filter((gallery) => !held.has(gallery.id))
  const frozen = disabled || busy
  return (
    <div className="photo-assets photo-galleries" aria-label="In galleries">
      <strong>In galleries</strong>
      {items.length ? (
        <ul>
          {items.map((gallery) => (
            <li key={gallery.id}>
              <Button
                variant="outline"
                size="sm"
                disabled={frozen}
                aria-label={`Remove from ${gallery.title}`}
                onClick={() => void change(gallery.id, false)}
              >
                {gallery.title}
                <X aria-hidden="true" size={14} />
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p>Not in a gallery yet.</p>
      )}
      {others.length > 0 && (
        <div className="gallery-add-one">
          <label>
            Add to gallery
            <select
              value={choice}
              disabled={frozen}
              onChange={(event) => setChoice(event.target.value)}
            >
              <option value="">Choose a gallery</option>
              {others.map((gallery) => (
                <option key={gallery.id} value={gallery.id}>
                  {gallery.title}
                </option>
              ))}
            </select>
          </label>
          <Button
            variant="outline"
            disabled={frozen || !choice}
            onClick={() => void change(choice, true)}
          >
            Add
          </Button>
        </div>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
