import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import type { SavedChatPhoto } from './ChatPhotoPicker'

export function ChatPhotoUpload({
  csrfToken,
  disabled,
  onStart,
  onSaved,
  onBusy,
}: {
  csrfToken: string
  disabled: boolean
  onStart: () => void
  onSaved: (photo: SavedChatPhoto) => void
  onBusy: (busy: boolean) => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [purpose, setPurpose] = useState('photo')
  const [busy, setBusy] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const input = useRef<HTMLInputElement>(null)
  const controller = useRef<AbortController | null>(null)
  useEffect(() => () => controller.current?.abort(), [])

  async function upload() {
    if (!file || disabled || controller.current) return
    if (
      !file.size ||
      file.size > 8 * 1024 * 1024 ||
      (file.type &&
        !['image/jpeg', 'image/png', 'image/webp'].includes(file.type))
    ) {
      setError('Choose a nonempty JPEG, PNG or WebP no larger than 8 MiB.')
      return
    }
    const pending = new AbortController()
    controller.current = pending
    setBusy(true)
    onBusy(true)
    onStart()
    setError('')
    setMessage('')
    try {
      const response = await fetch(`/api/photos?purpose=${purpose}`, {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        signal: pending.signal,
        headers: {
          'Content-Type': 'application/octet-stream',
          'X-CSRF-Token': csrfToken,
          'X-File-Name': encodeURIComponent(file.name),
        },
        body: file,
      })
      if (pending.signal.aborted) return
      if (!response.ok && response.status < 500) {
        setUncertain(false)
        setError(
          'Photo was not accepted. Check the file, storage limit and session, then try again.',
        )
        return
      }
      if (!response.ok) throw new Error('Upload status unknown')
      const photo: SavedChatPhoto = await response.json()
      if (pending.signal.aborted) return
      setUncertain(false)
      setFile(null)
      if (input.current) input.current.value = ''
      onSaved(photo)
      setMessage('Photo saved privately. Uploading made no AI request.')
    } catch {
      if (!pending.signal.aborted) {
        setUncertain(true)
        setError(
          'Upload outcome is unknown. Retry the same file safely, or check Photos. Leaving Chat does not delete a saved original.',
        )
      }
    } finally {
      if (!pending.signal.aborted) {
        controller.current = null
        setBusy(false)
        onBusy(false)
      }
    }
  }

  return (
    <section
      className="chat-photo-upload"
      aria-label="Upload a private photo in Chat"
    >
      <h4>Or upload a new photo</h4>
      <p>
        JPEG, PNG or WebP, up to 8 MiB. Originals stay in your private Photos
        library even if you leave Chat. Saving does not send an image to AI or
        add an inventory item.
      </p>
      <label>
        Upload a photo in Chat
        <input
          ref={input}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          disabled={disabled || busy || uncertain}
          onChange={(event) => {
            setFile(event.target.files?.[0] ?? null)
            setError('')
            setMessage('')
          }}
        />
      </label>
      <label>
        Chat photo purpose
        <select
          value={purpose}
          disabled={disabled || busy || uncertain}
          onChange={(event) => setPurpose(event.target.value)}
        >
          <option value="photo">General photo</option>
          <option value="receipt">Receipt</option>
          <option value="nameplate">Nameplate</option>
        </select>
      </label>
      <Button
        type="button"
        variant="outline"
        disabled={disabled || busy || !file}
        onClick={() => void upload()}
      >
        {busy
          ? 'Saving photo…'
          : uncertain
            ? 'Retry same photo upload'
            : 'Save photo privately'}
      </Button>
      {busy && <p role="status">Saving your private original…</p>}
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  )
}
