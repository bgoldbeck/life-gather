import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'

export function RecordExportPanel({
  csrfToken,
  refreshSession,
}: {
  csrfToken: string
  refreshSession?: () => Promise<void>
}) {
  const [busy, setBusy] = useState(false)
  const [includeOriginals, setIncludeOriginals] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const active = useRef<AbortController | null>(null)
  const urls = useRef(new Set<string>())
  useEffect(() => {
    const downloads = urls.current
    return () => {
      active.current?.abort()
      for (const url of downloads) URL.revokeObjectURL(url)
      downloads.clear()
    }
  }, [])

  async function download() {
    if (active.current) return
    const archive = includeOriginals
    const controller = new AbortController()
    active.current = controller
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const response = await fetch(
        archive ? '/api/export/archive' : '/api/export/records',
        {
          method: 'POST',
          credentials: 'same-origin',
          cache: 'no-store',
          signal: controller.signal,
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrfToken,
          },
          body: '{}',
        },
      )
      if (controller.signal.aborted) return
      if (response.status === 401) {
        await refreshSession?.()
        throw new Error('Your session expired. Sign in again before exporting.')
      }
      if (response.status === 413)
        throw new Error(
          archive
            ? 'Your archive exceeds the download limit. Download the JSON records and individual originals separately, or ask the installation owner for help.'
            : 'Your records exceed the download limit. Ask the installation owner for help.',
        )
      if (archive && response.status === 409)
        throw new Error(
          'Some saved originals could not be verified. No archive was downloaded. Ask the installation owner for help.',
        )
      if (!response.ok)
        throw new Error('Unable to prepare your export. Please try again.')
      if (
        !response.headers
          .get('Content-Type')
          ?.startsWith(archive ? 'application/zip' : 'application/json')
      )
        throw new Error(
          archive
            ? 'The server did not return an archive file. Please try again.'
            : 'The server did not return a records file. Please try again.',
        )
      const blob = await response.blob()
      if (controller.signal.aborted) return
      if (!blob.size || blob.size > (archive ? 64 : 16) * 1024 * 1024)
        throw new Error(
          archive
            ? 'The archive file has an unexpected size. Please try again.'
            : 'The records file has an unexpected size. Please try again.',
        )
      let valid = false
      try {
        if (archive && blob.size >= 52) {
          const header = new Uint8Array(await blob.slice(0, 4).arrayBuffer())
          const footer = new Uint8Array(
            await blob.slice(-22, -18).arrayBuffer(),
          )
          valid =
            header[0] === 80 &&
            header[1] === 75 &&
            header[2] === 3 &&
            header[3] === 4 &&
            footer[0] === 80 &&
            footer[1] === 75 &&
            footer[2] === 5 &&
            footer[3] === 6
        } else if (!archive) {
          const file: unknown = JSON.parse(await blob.text())
          valid =
            typeof file === 'object' &&
            file !== null &&
            'format' in file &&
            (file.format === 'lifegather-records/1' ||
              file.format === 'lifegather-records/2' ||
              file.format === 'lifegather-records/3' ||
              file.format === 'lifegather-records/4' ||
              file.format === 'lifegather-records/5' ||
              file.format === 'lifegather-records/6')
        }
      } catch {
        // A successful HTTP response must still contain the expected file format.
      }
      if (controller.signal.aborted) return
      if (!valid)
        throw new Error(
          archive
            ? 'The server did not return a valid archive file. Please try again.'
            : 'The server did not return a valid records file. Please try again.',
        )
      const url = URL.createObjectURL(blob)
      urls.current.add(url)
      const anchor = document.createElement('a')
      anchor.href = url
      const filename = response.headers
        .get('Content-Disposition')
        ?.match(
          archive
            ? /^attachment; filename="(lifegather-archive-\d{8}T\d{6}Z\.zip)"$/
            : /^attachment; filename="(lifegather-records-\d{8}T\d{6}Z\.json)"$/,
        )?.[1]
      anchor.download =
        filename ??
        (archive ? 'lifegather-archive.zip' : 'lifegather-records.json')
      document.body.appendChild(anchor)
      try {
        anchor.click()
      } finally {
        anchor.remove()
        // Let the browser acquire the download before releasing its object URL.
        window.setTimeout(() => {
          if (urls.current.delete(url)) URL.revokeObjectURL(url)
        }, 1000)
      }
      setNotice(
        archive
          ? 'Your records and originals download has started. Keep the archive private.'
          : 'Your records download has started. Keep the file private.',
      )
    } catch (caught) {
      if (!controller.signal.aborted)
        setError((caught as Error).message || 'Unable to prepare your export.')
    } finally {
      if (!controller.signal.aborted) {
        active.current = null
        setBusy(false)
      }
    }
  }

  return (
    <section className="settings-card" aria-labelledby="record-export-heading">
      <h2 id="record-export-heading">Download your records</h2>
      <p>
        Save a JSON copy of your evidence text, graph facts and correction
        history, reviewed purchases and quantities, conversations, and
        photo/document metadata and extracted text, and maintenance tasks with
        their revisions. Includes historical and unverified records with their
        original IDs, sources and status.
      </p>
      <p>
        Original images and document files are excluded from JSON. Choose ZIP
        below to include your active saved originals. Stored credentials,
        sign-in data, settings, scan schedules and processing caches remain
        excluded. This is a records copy, not a complete backup. Only the ZIP
        archive can be restored, into an account with no saved records.
        Installation recovery remains the installation owner's responsibility.
      </p>
      <p>
        Up to 10,000 records and 16 MiB. If your export exceeds either limit, no
        partial file is downloaded. The file contains your private saved
        content; choose where to keep it carefully. Downloading changes no saved
        records and makes no AI request.
      </p>
      <label className="consent-label">
        <input
          type="checkbox"
          checked={includeOriginals}
          disabled={busy}
          onChange={(event) => {
            setIncludeOriginals(event.target.checked)
            setError('')
            setNotice('')
          }}
        />
        Include original photos and documents (ZIP)
      </label>
      {includeOriginals && (
        <p>
          ZIP includes records, active original files and a hash manifest from
          one snapshot. Up to 1,000 originals and 64 MiB total, including
          records and archive metadata. Deleted originals and previews are
          excluded. The ZIP is not encrypted; keep it private.
        </p>
      )}
      <Button variant="outline" disabled={busy} onClick={() => void download()}>
        {busy
          ? includeOriginals
            ? 'Preparing archive…'
            : 'Preparing records…'
          : includeOriginals
            ? 'Download archive (ZIP)'
            : 'Download records (JSON)'}
      </Button>
      {busy && (
        <p role="status">
          {includeOriginals
            ? 'Preparing one consistent copy of your records and originals…'
            : 'Preparing one consistent copy of your records…'}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  )
}
