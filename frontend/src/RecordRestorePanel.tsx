import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'

const MAX_ARCHIVE_BYTES = 64 * 1024 * 1024

type RestoreResult = {
  snapshot_at: string
  total_records: number
  originals: number
}

export function RecordRestorePanel({
  csrfToken,
  refreshSession,
}: {
  csrfToken: string
  refreshSession?: () => Promise<void>
}) {
  const [file, setFile] = useState<File | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<RestoreResult | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const active = useRef<AbortController | null>(null)
  useEffect(() => () => active.current?.abort(), [])

  async function restore() {
    if (active.current || !file || !confirmed) return
    const controller = new AbortController()
    active.current = controller
    setBusy(true)
    setError('')
    setResult(null)
    try {
      if (!file.size || file.size > MAX_ARCHIVE_BYTES)
        throw new Error('Choose a personal archive ZIP of at most 64 MiB.')
      const response = await fetch('/api/import/archive', {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/zip',
          'X-CSRF-Token': csrfToken,
        },
        body: file,
      })
      if (controller.signal.aborted) return
      if (response.status === 401) {
        await refreshSession?.()
        throw new Error('Your session expired. Sign in again before restoring.')
      }
      let detail = ''
      try {
        const body: unknown = await response.clone().json()
        if (
          typeof body === 'object' &&
          body !== null &&
          'detail' in body &&
          typeof body.detail === 'string'
        )
          detail = body.detail
      } catch {
        // Error bodies without JSON fall back to the general message below.
      }
      if (response.status === 409)
        throw new Error(detail || 'This account cannot take this archive.')
      if (response.status === 413)
        throw new Error('The archive exceeds the 64 MiB restore limit.')
      if (response.status === 422)
        throw new Error(
          `${detail || 'This file is not a valid personal archive'}. Nothing was restored.`,
        )
      if (response.status === 429)
        throw new Error('Another restore is running. Try again shortly.')
      if (!response.ok)
        throw new Error('Unable to restore the archive. Nothing was restored.')
      const data = (await response.json()) as RestoreResult
      if (controller.signal.aborted) return
      setResult(data)
      setFile(null)
      setConfirmed(false)
      if (input.current) input.current.value = ''
    } catch (caught) {
      if (!controller.signal.aborted)
        setError((caught as Error).message || 'Unable to restore the archive.')
    } finally {
      if (!controller.signal.aborted) {
        active.current = null
        setBusy(false)
      }
    }
  }

  return (
    <section className="settings-card" aria-labelledby="record-restore-heading">
      <h2 id="record-restore-heading">Restore your records</h2>
      <p>
        Bring back a personal archive ZIP downloaded above, for example after
        moving to a new installation. Your records, history, corrections,
        purchases, conversations and original photos and documents return with
        their original IDs and dates.
      </p>
      <p>
        Restore works only into an account with no saved records, and only when
        those records are not already in this installation. Every file and hash
        is checked first; if anything does not match, nothing is restored.
        Settings, credentials and scan schedules are not part of the archive.
      </p>
      <label className="consent-label">
        Personal archive (ZIP)
        <input
          ref={input}
          type="file"
          accept=".zip,application/zip"
          disabled={busy}
          onChange={(event) => {
            setFile(event.target.files?.[0] ?? null)
            setError('')
            setResult(null)
          }}
        />
      </label>
      <label className="consent-label">
        <input
          type="checkbox"
          checked={confirmed}
          disabled={busy || !file}
          onChange={(event) => setConfirmed(event.target.checked)}
        />
        Add this archive&apos;s records to my account
      </label>
      <Button
        variant="outline"
        disabled={busy || !file || !confirmed}
        onClick={() => void restore()}
      >
        {busy ? 'Restoring…' : 'Restore archive'}
      </Button>
      {busy && <p role="status">Checking and restoring your archive…</p>}
      {result && (
        <p role="status">
          Restored {result.total_records.toLocaleString()} records and{' '}
          {result.originals.toLocaleString()} original files from the archive
          made {new Date(result.snapshot_at).toLocaleString()}.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  )
}
