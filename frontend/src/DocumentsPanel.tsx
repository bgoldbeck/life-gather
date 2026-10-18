import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { EvidencePanel, type EvidenceSource } from './EvidencePanel'
import './documents.css'

type Document = {
  id: string
  filename: string
  size: number
  pages: number
  extracted_text?: string
  text_truncated: boolean
  source_id: string | null
  updated_at: number
  deleted_at: number | null
}
type Page = { items: Document[]; next_cursor: string | null }
type Request = (path: string, init?: RequestInit) => Promise<unknown>

function DocumentEditor({
  initial,
  request,
  onChanged,
}: {
  initial: Document
  request: Request
  onChanged: () => Promise<void>
}) {
  const [doc, setDoc] = useState(initial)
  const [text, setText] = useState(initial.extracted_text ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [acknowledged, setAcknowledged] = useState(false)
  const [source, setSource] = useState<
    (EvidenceSource & { next_offset: number | null }) | null
  >(null)
  const sourceVersion = useRef(0)
  const active = useRef(true)
  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
    }
  }, [])
  async function save(event: FormEvent) {
    event.preventDefault()
    if (busy || !text.trim()) return
    setBusy(true)
    setError('')
    setStatus('')
    try {
      const next = (await request('documents/text', {
        method: 'POST',
        body: JSON.stringify({
          document_id: doc.id,
          text,
          expected_updated_at: doc.updated_at,
        }),
      })) as Document
      if (!active.current) return
      setDoc(next)
      setStatus('Reviewed text saved. No assets were created.')
      await onChanged()
    } catch {
      if (active.current)
        setError(
          'Unable to save reviewed text. Reload the document if it changed.',
        )
    } finally {
      if (active.current) setBusy(false)
    }
  }
  async function openSource(id: string, offset = 0) {
    const version = ++sourceVersion.current
    try {
      const next = await request(`chat/sources/${id}?offset=${offset}`)
      if (active.current && version === sourceVersion.current)
        setSource(next as EvidenceSource & { next_offset: number | null })
    } catch {
      if (active.current) setError('Unable to open the reviewed source.')
    }
  }
  async function remove() {
    if (busy || !acknowledged) return
    setBusy(true)
    setError('')
    try {
      const next = (await request('documents/delete', {
        method: 'POST',
        body: JSON.stringify({
          document_id: doc.id,
          expected_updated_at: doc.updated_at,
        }),
      })) as Document
      if (!active.current) return
      setDoc(next)
      setText('')
      setStatus(
        'Original PDF and extraction deleted. Saved source history is retained.',
      )
      await onChanged()
    } catch {
      if (active.current)
        setError('Unable to delete. Reload the document if it changed.')
    } finally {
      if (active.current) setBusy(false)
    }
  }
  return (
    <section className="document-editor" aria-label="PDF review">
      <h2>{doc.filename}</h2>
      <p>
        {doc.pages} page(s) · {(doc.size / 1048576).toFixed(2)} MiB
      </p>
      {error && <p role="alert">{error}</p>}
      {status && <p role="status">{status}</p>}
      {doc.deleted_at === null ? (
        <>
          <a href={`/api/documents/${doc.id}/original`} download>
            Download original PDF
          </a>
          <p>
            PDF text may lose layout or omit scanned content. Compare it with
            the original before saving. No PDF scripts or links are run by
            extraction.
          </p>
          {doc.text_truncated && (
            <p role="status">
              Extraction was limited to the first 4,000 characters. The complete
              original PDF is preserved.
            </p>
          )}
          {!doc.extracted_text?.trim() && (
            <p>
              No readable text was extracted. Enter a transcription or upload
              page photos in Photos; OCR is not included here.
            </p>
          )}
          <details>
            <summary>Original automatic extraction</summary>
            <pre>{doc.extracted_text || 'No extracted text.'}</pre>
          </details>
          {!doc.source_id && (
            <form onSubmit={(e) => void save(e)}>
              <label>
                Reviewed text
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  required
                  maxLength={4000}
                  disabled={busy}
                />
              </label>
              <Button type="submit" disabled={busy || !text.trim()}>
                Save reviewed text to memory
              </Button>
            </form>
          )}
          <details>
            <summary>Delete original PDF</summary>
            <p>
              Deletion removes the original file and automatic extraction
              permanently. Reviewed text, facts and their history remain in
              memory.
            </p>
            <label>
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(e) => setAcknowledged(e.target.checked)}
                disabled={busy}
              />
              I understand the original cannot be recovered here
            </label>
            <Button
              variant="outline"
              disabled={busy || !acknowledged}
              onClick={() => void remove()}
            >
              Delete original and extraction
            </Button>
          </details>
        </>
      ) : (
        <p>The original PDF has been deleted.</p>
      )}
      {doc.source_id && (
        <Button
          variant="outline"
          onClick={() => void openSource(doc.source_id!)}
        >
          Open reviewed text and corrections
        </Button>
      )}
      {source && (
        <EvidencePanel
          key={source.id}
          source={source}
          nextOffset={source.next_offset}
          opening={false}
          onOpen={openSource}
          onClose={() => {
            sourceVersion.current++
            setSource(null)
          }}
          request={(path, init) => request('chat' + path, init)}
        />
      )}
    </section>
  )
}

export function DocumentsPanel({
  csrfToken,
  refreshSession,
}: {
  csrfToken: string
  refreshSession?: () => Promise<void>
}) {
  const [page, setPage] = useState<Page | null>(null)
  const [selected, setSelected] = useState<Document | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const uploadAbort = useRef<AbortController | null>(null)
  const active = useRef(true)
  const selectionVersion = useRef(0)
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
      if (response.status === 401) await refreshSession?.()
      if (!response.ok) throw new Error('PDF request failed')
      return response.json()
    },
    [csrfToken, refreshSession],
  )
  const load = useCallback(async () => {
    const data = (await request('documents')) as Page
    if (active.current) setPage(data)
  }, [request])
  useEffect(() => {
    active.current = true
    const controller = new AbortController()
    request('documents', { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) setPage(data as Page)
      })
      .catch(() => {
        if (!controller.signal.aborted) setError('Unable to load PDFs.')
      })
    return () => {
      active.current = false
      controller.abort()
      uploadAbort.current?.abort()
    }
  }, [request])
  async function upload(event: FormEvent) {
    event.preventDefault()
    if (busy || !file) return
    if (file.size > 8 * 1024 * 1024) {
      setError('Choose a PDF no larger than 8 MiB.')
      return
    }
    setBusy(true)
    setError('')
    const controller = new AbortController()
    uploadAbort.current = controller
    try {
      const doc = (await request('documents', {
        method: 'POST',
        body: file,
        headers: {
          'Content-Type': 'application/pdf',
          'X-File-Name': encodeURIComponent(file.name),
        },
        signal: controller.signal,
      })) as Document
      if (!active.current) return
      selectionVersion.current++
      setSelected(doc)
      await load()
    } catch {
      if (active.current)
        setError(
          'Unable to upload. Choose a readable, unencrypted PDF of at most 8 MiB and 10 pages, then retry.',
        )
    } finally {
      if (active.current) setBusy(false)
    }
  }
  async function open(id: string) {
    const version = ++selectionVersion.current
    try {
      const doc = (await request('documents/' + id)) as Document
      if (active.current && version === selectionVersion.current)
        setSelected(doc)
    } catch {
      if (active.current) setError('Unable to open this PDF.')
    }
  }
  async function more() {
    if (!page?.next_cursor || busy) return
    setBusy(true)
    try {
      const next = (await request(
        'documents?cursor=' + page.next_cursor,
      )) as Page
      if (active.current)
        setPage((current) => ({
          ...next,
          items: [
            ...new Map(
              [...(current?.items ?? []), ...next.items].map((row) => [
                row.id,
                row,
              ]),
            ).values(),
          ],
        }))
    } catch {
      if (active.current) setError('Unable to load more PDFs.')
    } finally {
      if (active.current) setBusy(false)
    }
  }
  return (
    <section className="documents-panel">
      <h1>Documents</h1>
      <p>
        Private PDF evidence. Review extracted text before making it searchable
        in memory.
      </p>
      {error && <p role="alert">{error}</p>}
      <form onSubmit={(e) => void upload(e)}>
        <label>
          PDF file
          <input
            type="file"
            accept=".pdf,application/pdf"
            disabled={busy}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <p>
          Up to 8 MiB and 10 pages. Scanned PDFs may need a manual
          transcription.
        </p>
        <Button type="submit" disabled={busy || !file}>
          Upload PDF
        </Button>
      </form>
      {busy && <p role="status">Working on your private PDF…</p>}
      {page && !page.items.length && <p>No PDFs uploaded yet.</p>}
      <ul>
        {page?.items.map((doc) => (
          <li key={doc.id}>
            <Button variant="outline" onClick={() => void open(doc.id)}>
              {doc.filename} ·{' '}
              {doc.source_id ? 'Reviewed text saved' : 'Needs text review'}
            </Button>
          </li>
        ))}
      </ul>
      {page?.next_cursor && (
        <Button disabled={busy} onClick={() => void more()}>
          More PDFs
        </Button>
      )}
      {selected && (
        <DocumentEditor
          key={`${selected.id}:${selected.updated_at}`}
          initial={selected}
          request={request}
          onChanged={load}
        />
      )}
    </section>
  )
}
