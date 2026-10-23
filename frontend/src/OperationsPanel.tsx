import { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import './operations.css'

type Event = {
  level: string
  logger: string
  message: string
  details: Record<string, string | number>
  count: number
  first_at: number
  last_at: number
  alerted_at: number | null
}
export type OperationsOverview = {
  checked_at: number
  background_mode: string
  alerts: { webhook: boolean; email: boolean }
  jobs: {
    queued: number
    running: number
    completed_7d: number
    failed_7d: number
    canceled_7d: number
  }
  stuck: {
    expired_leases: number
    long_queued: number
    overdue_schedules: number
  }
  failures: { handler: string; count: number; last_at: number }[]
  schedules: { enabled: number; paused: number }
  events: Event[]
  storage: {
    accounts: number
    photos: number
    documents: number
    photo_bytes: number
    document_bytes: number
    total_bytes: number
    largest: {
      account: string
      photos: number
      documents: number
      bytes: number
    }[]
    quota_bytes: number | null
  }
}

const scanNames: Record<string, string> = {
  gmail_import: 'Gmail receipts',
  gmail_attachments: 'Gmail attachments',
  gmail_discovery: 'Gmail discovery',
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let size = value / 1024
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${size.toFixed(size < 10 ? 1 : 0)} ${units[unit]}`
}

function when(seconds: number): string {
  return new Date(seconds * 1000).toLocaleString()
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="operations-stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

const failedText = 'Unable to load the operations view.'

async function fetchOverview(
  signal: AbortSignal | undefined,
  refreshSession?: () => Promise<void>,
): Promise<OperationsOverview> {
  const response = await fetch('/api/operator/overview', {
    credentials: 'same-origin',
    cache: 'no-store',
    signal,
  })
  if (response.status === 401) await refreshSession?.()
  if (!response.ok) throw new Error(failedText)
  return (await response.json()) as OperationsOverview
}

export function OperationsPanel({
  refreshSession,
}: {
  refreshSession?: () => Promise<void>
}) {
  const [overview, setOverview] = useState<OperationsOverview | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(true)
  const load = useCallback(
    (signal?: AbortSignal) =>
      fetchOverview(signal, refreshSession)
        .then((data) => {
          if (signal?.aborted) return
          setOverview(data)
          setError('')
        })
        .catch((caught: unknown) => {
          if (signal?.aborted) return
          setError(
            caught instanceof Error && caught.name !== 'AbortError'
              ? caught.message
              : failedText,
          )
        })
        .finally(() => {
          if (!signal?.aborted) setBusy(false)
        }),
    [refreshSession],
  )
  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

  const stuck = overview
    ? overview.stuck.expired_leases +
      overview.stuck.long_queued +
      overview.stuck.overdue_schedules
    : 0
  return (
    <section className="operations-panel" aria-label="Operations">
      <h1>Operations</h1>
      <p>
        How this installation is running, across every account. Counts only: no
        one&apos;s records, files or messages appear here.
      </p>
      <div className="action-row">
        <Button
          variant="outline"
          disabled={busy}
          onClick={() => {
            setBusy(true)
            setError('')
            void load()
          }}
        >
          <RefreshCw aria-hidden="true" size={15} />
          {busy ? 'Checking…' : 'Refresh'}
        </Button>
        {overview && (
          <span className="operations-checked">
            Checked {when(overview.checked_at)}
          </span>
        )}
      </div>
      {error && (
        <p role="alert" className="operations-error">
          {error}
        </p>
      )}
      {!overview && busy && <p aria-live="polite">Loading operations…</p>}
      {overview && (
        <>
          <h2>
            Background jobs{' '}
            {stuck ? (
              <Badge variant="destructive">{stuck} stuck</Badge>
            ) : (
              <Badge variant="secondary">Nothing stuck</Badge>
            )}
          </h2>
          <div className="operations-grid">
            <Stat label="Queued scans" value={overview.jobs.queued} />
            <Stat label="Running scans" value={overview.jobs.running} />
            <Stat
              label="Finished (7 days)"
              value={overview.jobs.completed_7d}
            />
            <Stat label="Failed (7 days)" value={overview.jobs.failed_7d} />
            <Stat
              label="Active schedules"
              value={`${overview.schedules.enabled} (${overview.schedules.paused} paused)`}
            />
            <Stat
              label="Background mode"
              value={
                overview.background_mode === 'external'
                  ? 'Outside scheduler'
                  : 'Built in'
              }
            />
          </div>
          {stuck > 0 && (
            <ul className="operations-list" aria-label="Stuck jobs">
              {overview.stuck.expired_leases > 0 && (
                <li>
                  {overview.stuck.expired_leases} running scan(s) stopped
                  renewing their lease and were not picked up again.
                </li>
              )}
              {overview.stuck.long_queued > 0 && (
                <li>
                  {overview.stuck.long_queued} scan(s) have waited in the queue
                  for over 30 minutes.
                </li>
              )}
              {overview.stuck.overdue_schedules > 0 && (
                <li>
                  {overview.stuck.overdue_schedules} schedule(s) are over an
                  hour late. Check that the scheduler or tick is running.
                </li>
              )}
            </ul>
          )}
          <h3>Failures by scan type (7 days)</h3>
          {overview.failures.length ? (
            <ul className="operations-list">
              {overview.failures.map((failure) => (
                <li key={failure.handler}>
                  {scanNames[failure.handler] ?? failure.handler}:{' '}
                  {failure.count} failed, last {when(failure.last_at)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty-state">No failed scans in the last 7 days.</p>
          )}

          <h2>Recent problems</h2>
          <p className="operations-note">
            Alerts:{' '}
            {overview.alerts.webhook || overview.alerts.email
              ? [
                  overview.alerts.webhook && 'webhook',
                  overview.alerts.email && 'operator email',
                ]
                  .filter(Boolean)
                  .join(' and ')
              : 'none configured. Set LIFEGATHER_ALERT_WEBHOOK_URL, or SMTP with LIFEGATHER_OPERATOR_EMAILS, to be told about new problems.'}
          </p>
          {overview.events.length ? (
            <div className="operations-table-wrap">
              <table className="operations-table">
                <thead>
                  <tr>
                    <th scope="col">Problem</th>
                    <th scope="col">Where</th>
                    <th scope="col">Times</th>
                    <th scope="col">Last seen</th>
                    <th scope="col">Alerted</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.events.map((event) => (
                    <tr
                      key={`${event.logger}-${event.message}-${JSON.stringify(event.details)}`}
                    >
                      <td>{event.message}</td>
                      <td>
                        {Object.entries(event.details)
                          .map(([name, value]) => `${name}: ${value}`)
                          .join(', ') || event.logger}
                      </td>
                      <td>{event.count}</td>
                      <td>{when(event.last_at)}</td>
                      <td>{event.alerted_at ? when(event.alerted_at) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="empty-state">
              No problems recorded in the last 30 days.
            </p>
          )}

          <h2>Storage</h2>
          <div className="operations-grid">
            <Stat
              label="Stored files"
              value={formatBytes(overview.storage.total_bytes)}
            />
            <Stat
              label="Photos"
              value={`${overview.storage.photos} · ${formatBytes(overview.storage.photo_bytes)}`}
            />
            <Stat
              label="Documents"
              value={`${overview.storage.documents} · ${formatBytes(overview.storage.document_bytes)}`}
            />
            <Stat label="Accounts" value={overview.storage.accounts} />
            <Stat
              label="Per-account limit"
              value={
                overview.storage.quota_bytes === null
                  ? 'No limit'
                  : formatBytes(overview.storage.quota_bytes)
              }
            />
          </div>
          {overview.storage.largest.length > 0 && (
            <>
              <h3>Largest accounts</h3>
              <ul className="operations-list" aria-label="Largest accounts">
                {overview.storage.largest.map((account) => (
                  <li key={account.account}>
                    {account.account}: {formatBytes(account.bytes)} (
                    {account.photos} photos, {account.documents} documents)
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </section>
  )
}
