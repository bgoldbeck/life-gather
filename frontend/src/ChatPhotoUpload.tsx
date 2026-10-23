import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import type { SavedChatPhoto } from './ChatPhotoPicker'
import {
  CameraCaptureButton,
  CANCELLED_MESSAGE,
  PhotoUploadProgress,
} from './PhotoCapture'
import { PHOTO_ACCEPT, photoFileProblem, sendPhoto } from './photoUpload'

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
  const [percent, setPercent] = useState(0)
  const [uncertain, setUncertain] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const input = useRef<HTMLInputElement>(null)
  const controller = useRef<AbortController | null>(null)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      controller.current?.abort()
    }
  }, [])

  async function upload(chosen = file) {
    if (!chosen || disabled || controller.current) return
    const problem = photoFileProblem(chosen)
    if (problem) {
      setError(problem)
      setMessage('')
      return
    }
    const pending = new AbortController()
    controller.current = pending
    setBusy(true)
    setPercent(0)
    onBusy(true)
    onStart()
    setError('')
    setMessage('')
    const result = await sendPhoto<SavedChatPhoto>({
      url: `/api/photos?purpose=${purpose}`,
      file: chosen,
      csrfToken,
      signal: pending.signal,
      onProgress: (value) => mounted.current && setPercent(value),
    })
    if (!mounted.current) return
    controller.current = null
    setBusy(false)
    onBusy(false)
    if (result.kind === 'saved') {
      setUncertain(false)
      setFile(null)
      if (input.current) input.current.value = ''
      onSaved(result.photo)
      setMessage('Photo saved privately. Uploading made no AI request.')
    } else if (result.kind === 'cancelled') {
      setMessage(CANCELLED_MESSAGE)
    } else if (result.kind === 'rejected') {
      setUncertain(false)
      setError(
        'Photo was not accepted. Check the file, storage limit and session, then try again.',
      )
    } else {
      setUncertain(true)
      setError(
        'Upload outcome is unknown. Retry the same file safely, or check Photos. Leaving Chat does not delete a saved original.',
      )
    }
  }

  return (
    <section
      className="chat-photo-upload"
      aria-label="Upload a private photo in Chat"
    >
      <h4>Or add a new photo</h4>
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
          accept={PHOTO_ACCEPT}
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
      <CameraCaptureButton
        label="Take a photo for Chat"
        disabled={disabled || busy || uncertain}
        onCapture={(captured) => {
          setFile(captured)
          void upload(captured)
        }}
      />
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
      {file && !busy && <p>Photo ready to save: {file.name}</p>}
      {busy && (
        <>
          <p role="status">Saving your private original…</p>
          <PhotoUploadProgress
            percent={percent}
            onCancel={() => controller.current?.abort()}
          />
        </>
      )}
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  )
}
