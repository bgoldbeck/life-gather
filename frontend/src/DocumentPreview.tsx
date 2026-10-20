import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'

export type ExtractionMetadata = {
  warnings?: string[]
  sheets?: string[]
  sheet?: string
  encoding?: string
  delimiter?: string
  header?: boolean
}
type Preview = {
  text: string
  truncated: boolean
  metadata: ExtractionMetadata
}

export function DocumentPreview({
  id,
  format,
  metadata,
  request,
  onUse,
  disabled,
}: {
  id: string
  format: string
  metadata: ExtractionMetadata
  request: (path: string, init?: RequestInit) => Promise<unknown>
  onUse: (text: string) => void
  disabled: boolean
}) {
  const [sheet, setSheet] = useState(
    metadata.sheet ?? metadata.sheets?.[0] ?? '',
  )
  const [range, setRange] = useState('')
  const [encoding, setEncoding] = useState(metadata.encoding ?? 'utf-8-sig')
  const [delimiter, setDelimiter] = useState(metadata.delimiter ?? '')
  const [header, setHeader] = useState(metadata.header ?? true)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const active = useRef(true)
  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
    }
  }, [])
  if (!['xlsx', 'csv', 'txt', 'md'].includes(format)) return null
  async function load() {
    if (busy || disabled) return
    setBusy(true)
    setError('')
    setPreview(null)
    try {
      const result = (await request('documents/preview', {
        method: 'POST',
        body: JSON.stringify({
          document_id: id,
          sheet,
          cell_range: range,
          encoding,
          delimiter,
          header,
        }),
      })) as Preview
      if (active.current) setPreview(result)
    } catch {
      if (active.current)
        setError(
          'Unable to preview. Check encoding, delimiter or worksheet/range (up to 200 rows and 50 columns).',
        )
    } finally {
      if (active.current) setBusy(false)
    }
  }
  return (
    <fieldset disabled={busy || disabled} className="document-preview">
      <legend>Extraction selection</legend>
      {format === 'xlsx' ? (
        <>
          <label>
            Worksheet
            <select
              value={sheet}
              onChange={(e) => {
                setSheet(e.target.value)
                setPreview(null)
              }}
            >
              {metadata.sheets?.map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </label>
          <label>
            Cell range
            <input
              placeholder="A1:D20"
              value={range}
              maxLength={25}
              onChange={(e) => {
                setRange(e.target.value.toUpperCase())
                setPreview(null)
              }}
            />
          </label>
          <p>
            Default range A1:AX200. Formulas are never executed; stored values
            may be stale or unformatted.
          </p>
        </>
      ) : (
        <label>
          Text encoding
          <select
            value={encoding}
            onChange={(e) => {
              setEncoding(e.target.value)
              setPreview(null)
            }}
          >
            <option value="utf-8-sig">UTF-8</option>
            <option value="utf-16">UTF-16</option>
            <option value="cp1252">Windows-1252</option>
          </select>
        </label>
      )}
      {format === 'csv' && (
        <>
          <label>
            CSV delimiter
            <select
              value={delimiter}
              onChange={(e) => {
                setDelimiter(e.target.value)
                setPreview(null)
              }}
            >
              <option value="">Detect</option>
              <option value=",">Comma</option>
              <option value=";">Semicolon</option>
              <option value={'\t'}>Tab</option>
              <option value="|">Pipe</option>
            </select>
          </label>
          <label>
            <input
              type="checkbox"
              checked={header}
              onChange={(e) => {
                setHeader(e.target.checked)
                setPreview(null)
              }}
            />
            First row is a header
          </label>
        </>
      )}
      <Button type="button" onClick={() => void load()}>
        Preview selection
      </Button>
      {busy && <p role="status">Preparing preview…</p>}
      {error && <p role="alert">{error}</p>}
      {preview && (
        <>
          <pre>{preview.text || 'No readable text in this selection.'}</pre>
          {preview.metadata.warnings?.map((warning, i) => (
            <p key={i}>{warning}</p>
          ))}
          {preview.truncated && (
            <p role="status">Preview is partial; some content was omitted.</p>
          )}
          <p>
            Using this preview replaces the unsaved reviewed-text draft below.
          </p>
          <Button
            type="button"
            disabled={!preview.text.trim()}
            onClick={() => onUse(preview.text)}
          >
            Use preview as reviewed text
          </Button>
        </>
      )}
    </fieldset>
  )
}
