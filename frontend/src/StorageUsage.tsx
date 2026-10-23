import { useEffect, useState } from 'react'
import { formatBytes } from './formatBytes'
import './storage-usage.css'

type Usage = {
  used_bytes: number
  limit_bytes: number | null
  available_bytes: number | null
  photos: number
  photo_bytes: number
  documents: number
  document_bytes: number
}

export function StorageUsage({
  refreshSession,
}: {
  refreshSession?: () => Promise<void>
}) {
  const [usage, setUsage] = useState<Usage | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/storage/usage', {
      credentials: 'same-origin',
      cache: 'no-store',
      signal: controller.signal,
    })
      .then(async (response) => {
        if (response.status === 401) await refreshSession?.()
        if (!response.ok) throw new Error('Storage usage request failed')
        return (await response.json()) as Usage
      })
      .then((data) => {
        if (!controller.signal.aborted) setUsage(data)
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true)
      })
    return () => controller.abort()
  }, [refreshSession])

  const limit = usage?.limit_bytes ?? null
  const full = usage !== null && limit !== null && usage.used_bytes >= limit
  return (
    <section
      className="settings-card storage-usage"
      aria-labelledby="storage-usage-heading"
    >
      <h2 id="storage-usage-heading">File storage</h2>
      <p>
        Space your photos and documents take in this installation's file
        storage, including photo previews.
      </p>
      {failed ? (
        <p role="alert">Unable to load storage usage.</p>
      ) : usage === null ? (
        <p role="status">Loading storage usage…</p>
      ) : (
        <>
          <p className="storage-usage-total">
            {limit === null
              ? `${formatBytes(usage.used_bytes)} used · No limit`
              : `${formatBytes(usage.used_bytes)} of ${formatBytes(limit)} used`}
          </p>
          {limit !== null && (
            <progress
              aria-label="Storage used"
              max={limit}
              value={Math.min(usage.used_bytes, limit)}
            />
          )}
          <ul className="storage-usage-breakdown">
            <li>
              Photos: {usage.photos} ({formatBytes(usage.photo_bytes)})
            </li>
            <li>
              Documents: {usage.documents} ({formatBytes(usage.document_bytes)})
            </li>
          </ul>
          {full && (
            <p role="alert">
              Your storage is full. Delete photos or documents to add new ones.
            </p>
          )}
        </>
      )}
    </section>
  )
}
