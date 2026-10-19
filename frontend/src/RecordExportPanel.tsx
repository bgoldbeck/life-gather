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
    const controller = new AbortController()
    active.current = controller
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const response = await fetch('/api/export/records', {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: '{}',
      })
      if (controller.signal.aborted) return
      if (response.status === 401) {
        await refreshSession?.()
        throw new Error('Your session expired. Sign in again before exporting.')
      }
      if (response.status === 413)
        throw new Error(
          'Your records exceed the download limit. Ask the installation owner for a complete backup.',
        )
      if (!response.ok)
        throw new Error('Unable to prepare your export. Please try again.')
      if (!response.headers.get('Content-Type')?.startsWith('application/json'))
        throw new Error(
          'The server did not return a records file. Please try again.',
        )
      const blob = await response.blob()
      if (controller.signal.aborted) return
      if (!blob.size || blob.size > 16 * 1024 * 1024)
        throw new Error(
          'The records file has an unexpected size. Please try again.',
        )
      let valid = false
      try {
        const file: unknown = JSON.parse(await blob.text())
        valid =
          typeof file === 'object' &&
          file !== null &&
          'format' in file &&
          file.format === 'lifegather-records/1'
      } catch {
        // A successful HTTP response must still contain the expected file format.
      }
      if (controller.signal.aborted) return
      if (!valid)
        throw new Error(
          'The server did not return a valid records file. Please try again.',
        )
      const url = URL.createObjectURL(blob)
      urls.current.add(url)
      const anchor = document.createElement('a')
      anchor.href = url
      const filename = response.headers
        .get('Content-Disposition')
        ?.match(
          /^attachment; filename="(lifegather-records-\d{8}T\d{6}Z\.json)"$/,
        )?.[1]
      anchor.download = filename ?? 'lifegather-records.json'
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
      setNotice('Your records download has started. Keep the file private.')
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
        history, reviewed purchases and quantities, conversations, and photo/PDF
        metadata and extracted text. Includes historical and unverified records
        with their original IDs, sources and status.
      </p>
      <p>
        Original images and PDF files, stored credentials, sign-in data,
        settings, scan schedules and processing caches are excluded. This is a
        records copy, not a complete backup; it cannot be restored through the
        app. Download original files separately. A complete installation backup
        remains the installation owner's responsibility.
      </p>
      <p>
        Up to 10,000 records and 16 MiB. If your export exceeds either limit, no
        partial file is downloaded. The file contains your private saved
        content; choose where to keep it carefully. Downloading changes no saved
        records and makes no AI request.
      </p>
      <Button variant="outline" disabled={busy} onClick={() => void download()}>
        {busy ? 'Preparing records…' : 'Download records (JSON)'}
      </Button>
      {busy && (
        <p role="status">Preparing one consistent copy of your records…</p>
      )}
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  )
}
