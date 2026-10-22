import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ChatPhotoPicker } from './ChatPhotoPicker'

export type ChatAttachmentValue = {
  kind: 'photo' | 'document'
  id: string
  filename: string
}

type SavedDocument = { id: string; filename: string; format: string }

function DocumentPicker({
  disabled,
  onSelect,
}: {
  disabled: boolean
  onSelect: (document: SavedDocument) => void
}) {
  const [items, setItems] = useState<SavedDocument[]>([])
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
    try {
      const response = await fetch(
        `/api/documents?limit=5${more ? '&cursor=' + encodeURIComponent(cursor ?? '') : ''}`,
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
        const rows: SavedDocument[] = more ? [...old] : []
        const known = new Set(rows.map((row) => row.id))
        for (const row of page.items as SavedDocument[])
          if (!known.has(row.id)) {
            rows.push(row)
            known.add(row.id)
          }
        return rows
      })
      setCursor(page.next_cursor)
      if (!more && !page.items.length)
        setMessage('No saved private documents. Upload one in Documents first.')
    } catch {
      if (!pending.signal.aborted)
        setError('Unable to load saved documents. Try again.')
    } finally {
      if (!pending.signal.aborted) setBusy(false)
    }
  }
  return (
    <section aria-label="Choose a saved document for Chat">
      <Button
        type="button"
        variant="outline"
        disabled={disabled || busy}
        onClick={() => void load()}
      >
        Load saved documents
      </Button>
      <ul className="chat-attachment-list">
        {items.map((row) => (
          <li key={row.id}>
            <Button
              type="button"
              variant="outline"
              disabled={disabled || busy}
              aria-label={`Attach document ${row.filename}`}
              onClick={() => onSelect(row)}
            >
              {row.filename}
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
          More saved documents
        </Button>
      )}
      {busy && <p role="status">Loading saved document choices…</p>}
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  )
}

/** One optional photo or document the AI assistant may read and cite. */
export function ChatAttachment({
  csrfToken,
  selected,
  onSelect,
  disabled,
}: {
  csrfToken: string
  selected: ChatAttachmentValue | null
  onSelect: (value: ChatAttachmentValue | null) => void
  disabled: boolean
}) {
  const [choosing, setChoosing] = useState<'photo' | 'document' | null>(null)
  return (
    <section
      className="chat-attachment"
      aria-label="Attach a photo or document"
    >
      {selected ? (
        <p>
          Attached {selected.kind}: <strong>{selected.filename}</strong>.{' '}
          <Button
            type="button"
            variant="outline"
            disabled={disabled}
            onClick={() => onSelect(null)}
          >
            Remove attachment
          </Button>
        </p>
      ) : (
        <div className="chat-send">
          <Button
            type="button"
            variant="outline"
            disabled={disabled}
            aria-pressed={choosing === 'photo'}
            onClick={() => setChoosing(choosing === 'photo' ? null : 'photo')}
          >
            Attach a photo
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={disabled}
            aria-pressed={choosing === 'document'}
            onClick={() =>
              setChoosing(choosing === 'document' ? null : 'document')
            }
          >
            Attach a document
          </Button>
        </div>
      )}
      {!selected && choosing === 'photo' && (
        <ChatPhotoPicker
          csrfToken={csrfToken}
          selected={null}
          disabled={disabled}
          onSelect={(photo) => {
            if (!photo) return
            onSelect({ kind: 'photo', id: photo.id, filename: photo.filename })
            setChoosing(null)
          }}
        />
      )}
      {!selected && choosing === 'document' && (
        <DocumentPicker
          disabled={disabled}
          onSelect={(row) => {
            onSelect({ kind: 'document', id: row.id, filename: row.filename })
            setChoosing(null)
          }}
        />
      )}
      <p>
        Ask about the attached file or say which details to save. Your provider
        receives the document’s text, or the photo itself the first time it is
        read; its transcription is saved and reused. Details found in the file
        are saved with the file as evidence; ownership still needs your words.
      </p>
    </section>
  )
}
