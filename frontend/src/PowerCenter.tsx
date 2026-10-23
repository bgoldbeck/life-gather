import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Activity,
  ArrowUpRight,
  Archive,
  Camera,
  CircleHelp,
  Cloud,
  FileText,
  HardDrive,
  Landmark,
  Mail,
  MessageCircle,
  Package,
  Plug,
  RefreshCw,
  ScanSearch,
  Sparkles,
  Wrench,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { ForestScene, PowerGrowth } from './PowerGrowth'
import { ToneIcon, type Tone } from './tones'
import './power-center.css'

type Destination =
  'Settings' | 'Scans' | 'Documents' | 'Assets' | 'Maintenance' | 'Memories'
type State =
  'ready' | 'unknown' | 'stale' | 'blocked' | 'disabled' | 'failed' | 'planned'
type Capability = {
  id: string
  title: string
  weight: number
  state: State
  reason: string
  action: Destination
  available_to_request: boolean
}
type Source = {
  id: string
  title: string
  category: 'local' | 'ai' | 'email' | 'planned'
  configured: boolean
  state: State
  reason: string
  capabilities: string[]
  action: Destination
  last_success: number | null
  last_run_id?: string | null
  freshness: string
  scope: string
}
export type PowerSnapshot = {
  checked_at: number
  expires_at: number
  scoring_version: string
  score: number | null
  minimum_score: number
  maximum_score: number
  capabilities: Capability[]
  sources: Source[]
  issues: {
    id: string
    title: string
    reason: string
    action: Destination
    state: State
    run_id: string | null
  }[]
  issues_truncated: boolean
  connected_sources: number
  completed_scans_7d: number
  imported_messages_7d: number
  period_start: number
  ai_requests: number
  ai_limit: number
  ai_resets_at: number
  paused_schedules: number
}
const labels: Record<State, string> = {
  ready: 'Ready',
  unknown: 'Unverified',
  stale: 'Stale observation',
  blocked: 'Needs setup',
  disabled: 'Disabled',
  failed: 'Needs attention',
  planned: 'Planned',
}
// Icons and tones for known sources and capabilities; anything new falls back to power.
const sourceLooks: Record<string, [LucideIcon, Tone]> = {
  local: [HardDrive, 'assets'],
  banking: [Landmark, 'finance'],
  other_sources: [Cloud, 'documents'],
}
const categoryLooks: Record<Source['category'], [LucideIcon, Tone]> = {
  local: [HardDrive, 'assets'],
  ai: [Sparkles, 'ai'],
  email: [Mail, 'email'],
  planned: [Cloud, 'settings'],
}
const capabilityLooks: Record<string, [LucideIcon, Tone]> = {
  evidence: [FileText, 'documents'],
  inventory: [Package, 'assets'],
  maintenance: [Wrench, 'maintenance'],
  archive: [Archive, 'documents'],
  ai_recall: [MessageCircle, 'ai'],
  photo_reading: [Camera, 'photos'],
}
function capabilityLook(id: string): [LucideIcon, Tone] {
  return (
    capabilityLooks[id] ??
    (id.startsWith('gmail') ? [Mail, 'email'] : [Zap, 'power'])
  )
}
function StatePill({ state, label }: { state: State; label: string }) {
  return (
    <Badge variant="secondary" className="state-pill" data-state={state}>
      {label}
    </Badge>
  )
}
function when(timestamp: number) {
  return new Date(timestamp * 1000).toLocaleString()
}

export function PowerCenter({
  userId,
  onNavigate,
  onOpenScan,
  onOpenAssistant,
  refreshSession,
  compact = false,
  changeSignal = 0,
}: {
  userId: string
  onNavigate: (page: Destination) => void
  onOpenScan?: (id: string) => void
  onOpenAssistant?: () => void
  refreshSession?: () => Promise<void>
  compact?: boolean
  changeSignal?: number
}) {
  const [loaded, setLoaded] = useState<{
    key: string
    value: PowerSnapshot
  } | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(true)
  const [notice, setNotice] = useState('')
  const [connectionFilter, setConnectionFilter] = useState('all')
  const [category, setCategory] = useState('all')
  const [changes, setChanges] = useState<{
    newly: string[]
    lost: string[]
  } | null>(null)
  const [clock, setClock] = useState(() => Date.now() / 1000)
  const controller = useRef<AbortController | null>(null)
  const storageKey = `lifegather.power.capabilities.v1.${userId}`
  const snapshot = loaded?.key === storageKey ? loaded.value : null
  const load = useCallback(
    async (source?: string) => {
      controller.current?.abort()
      const request = new AbortController()
      controller.current = request
      setBusy(true)
      setError('')
      const timeout = window.setTimeout(() => {
        if (request.signal.aborted) return
        request.abort()
        setError('Local checks timed out. Retry Power Center.')
        setBusy(false)
      }, 15000)
      try {
        const response = await fetch('/api/power', {
          credentials: 'same-origin',
          cache: 'no-store',
          signal: request.signal,
        })
        if (request.signal.aborted) return
        if (response.status === 401) {
          await refreshSession?.()
          throw new Error('Your session expired. Sign in again.')
        }
        if (!response.ok)
          throw new Error(
            'Power Center is unavailable. Retry the local checks.',
          )
        const value = (await response.json()) as PowerSnapshot
        if (request.signal.aborted) return
        if (
          !Array.isArray(value.capabilities) ||
          !Array.isArray(value.sources) ||
          !Array.isArray(value.issues)
        )
          throw new Error(
            'Power Center returned an incomplete response. Retry the local checks.',
          )
        // Only capability IDs/booleans in per-account tab storage; no records, credentials or health logs.
        const available = value.capabilities
          .filter((c) => c.available_to_request)
          .map((c) => c.id)
        try {
          const raw = sessionStorage.getItem(storageKey)
          const previous: unknown = raw ? JSON.parse(raw) : null
          if (
            Array.isArray(previous) &&
            previous.every((id) => typeof id === 'string')
          ) {
            const newly = available.filter((id) => !previous.includes(id))
            const lost = previous.filter(
              (id) => !available.includes(id),
            ) as string[]
            if (newly.length || lost.length) setChanges({ newly, lost })
          }
          sessionStorage.setItem(storageKey, JSON.stringify(available))
        } catch {
          /* Storage is optional; current capability explanations remain available. */
        }
        setLoaded({ key: storageKey, value })
        setClock(Date.now() / 1000)
        if (source)
          setNotice(
            `Local observations refreshed for ${source}. No external probe or scan was run.`,
          )
      } catch (caught) {
        if (!request.signal.aborted)
          setError(
            caught instanceof Error
              ? caught.message
              : 'Unable to load Power Center.',
          )
      } finally {
        window.clearTimeout(timeout)
        if (!request.signal.aborted) setBusy(false)
      }
    },
    [refreshSession, storageKey],
  )
  useEffect(() => {
    const initial = window.setTimeout(() => void load(), 0)
    const refresh = window.setInterval(() => {
      if (!document.hidden) void load()
    }, 60000)
    const tick = window.setInterval(() => setClock(Date.now() / 1000), 30000)
    return () => {
      controller.current?.abort()
      window.clearTimeout(initial)
      window.clearInterval(refresh)
      window.clearInterval(tick)
    }
  }, [load, changeSignal])
  const stale = snapshot && clock >= snapshot.expires_at
  const title = (id: string) =>
    snapshot?.capabilities.find((c) => c.id === id)?.title ?? id
  const action = (page: Destination) => onNavigate(page)
  return (
    <section
      className={`power-center ${compact ? 'power-compact' : ''}`}
      aria-label={compact ? 'Connection capabilities' : 'Power Center'}
    >
      <div className="power-heading power-hero">
        {!compact && <ForestScene />}
        <div className="power-title">
          {!compact && <ToneIcon icon={Zap} tone="power" size={26} />}
          <div>
            {compact && (
              <p className="power-eyebrow">
                <Zap size={16} aria-hidden="true" /> YOUR WORKSPACE, EXPLAINED
              </p>
            )}
            {compact ? (
              <h2>What your connections enable</h2>
            ) : (
              <h1>Power Center</h1>
            )}
            <p>
              Understand what is available, what needs attention, and what to do
              next.
            </p>
          </div>
        </div>
        <Button
          variant="outline"
          disabled={busy}
          onClick={() => void load('all sources')}
        >
          <RefreshCw size={16} aria-hidden="true" />
          {busy ? 'Checking locally…' : 'Check all locally'}
        </Button>
        {!compact && snapshot && (
          <PowerGrowth
            score={snapshot.score}
            minimum={snapshot.minimum_score}
            maximum={snapshot.maximum_score}
            stale={!!stale}
          />
        )}
      </div>
      {error && (
        <div role="alert">
          <p>{error}</p>
          <Button variant="outline" disabled={busy} onClick={() => void load()}>
            Retry Power Center
          </Button>
        </div>
      )}
      {notice && <p role="status">{notice}</p>}
      {!snapshot ? (
        <p role="status">
          {error
            ? 'Capability status unavailable.'
            : 'Loading private capability status…'}
        </p>
      ) : (
        <>
          <p className="power-meta">
            Local checks: {when(snapshot.checked_at)}.{' '}
            {stale ? (
              <strong>Snapshot expired; status is stale.</strong>
            ) : (
              'Refreshes every minute while visible.'
            )}{' '}
            Checks read local state only. No ingestion or billable probes.
          </p>
          {changes && (
            <div className="power-changes" role="status">
              <h3>Capabilities changed</h3>
              {changes.newly.length > 0 && (
                <p>
                  <strong>Newly available to request:</strong>{' '}
                  {changes.newly.map(title).join(', ')}. External health may
                  still be unverified.
                </p>
              )}
              {changes.lost.length > 0 && (
                <p>
                  <strong>No longer available:</strong>{' '}
                  {changes.lost.map(title).join(', ')}.
                </p>
              )}
              <p>
                Availability does not mean a discovery or scan has happened.
              </p>
              <Button variant="ghost" onClick={() => setChanges(null)}>
                Dismiss capability changes
              </Button>
            </div>
          )}
          {!compact && (
            <>
              <div className="power-summary">
                <Card size="sm">
                  <CardContent>
                    <ToneIcon icon={Zap} tone="power" />
                    <span>
                      Power Level · catalog {snapshot.scoring_version}
                    </span>
                    <strong>
                      {stale
                        ? 'Stale'
                        : snapshot.score === null
                          ? 'Incomplete'
                          : `${snapshot.score}%`}
                    </strong>
                    <p>
                      {snapshot.score === null
                        ? `${snapshot.minimum_score} confirmed points; up to ${snapshot.maximum_score} if unverified/stale dependencies work.`
                        : `${snapshot.score} of 100 capability points ready. Other outcomes need setup or are disabled.`}
                    </p>
                  </CardContent>
                </Card>
                <Card size="sm">
                  <CardContent>
                    <ToneIcon icon={Plug} tone="graph" />
                    <span>Configured source providers / mailboxes</span>
                    <strong>{snapshot.connected_sources}</strong>
                    <p>Configuration is separate from verified health.</p>
                  </CardContent>
                </Card>
                <Card size="sm">
                  <CardContent>
                    <ToneIcon icon={ScanSearch} tone="email" />
                    <span>Completed scans · last 7 days</span>
                    <strong>{snapshot.completed_scans_7d}</strong>
                    <p>
                      {snapshot.imported_messages_7d} newly imported messages in
                      completed runs. These are not asset counts.
                    </p>
                  </CardContent>
                </Card>
              </div>
              <section aria-labelledby="power-sources">
                <div className="power-section-heading">
                  <h2 id="power-sources">
                    <Plug aria-hidden="true" size={21} /> Your connections
                  </h2>
                  <div className="power-filters">
                    <label>
                      Connection status
                      <select
                        value={connectionFilter}
                        onChange={(e) => setConnectionFilter(e.target.value)}
                      >
                        <option value="all">All connections</option>
                        <option value="connected">Configured</option>
                        <option value="not-connected">Not configured</option>
                      </select>
                    </label>
                    <label>
                      Source category
                      <select
                        value={category}
                        onChange={(e) => setCategory(e.target.value)}
                      >
                        <option value="all">All categories</option>
                        <option value="local">Local</option>
                        <option value="ai">AI</option>
                        <option value="email">Email</option>
                        <option value="planned">Planned</option>
                      </select>
                    </label>
                  </div>
                </div>
                <div className="power-sources">
                  {snapshot.sources
                    .filter(
                      (s) =>
                        (category === 'all' || s.category === category) &&
                        (connectionFilter === 'all' ||
                          s.configured === (connectionFilter === 'connected')),
                    )
                    .map((source) => {
                      const [icon, tone] =
                        sourceLooks[source.id] ?? categoryLooks[source.category]
                      return (
                        <Card
                          size="sm"
                          key={source.id}
                          className="power-source"
                          data-tone={tone}
                        >
                          <CardContent>
                            <div className="power-source-heading">
                              <ToneIcon icon={icon} tone={tone} size={20} />
                              <h3>{source.title}</h3>
                              {stale && source.state !== 'planned' ? (
                                <StatePill
                                  state="stale"
                                  label="Stale snapshot"
                                />
                              ) : (
                                <StatePill
                                  state={source.state}
                                  label={labels[source.state]}
                                />
                              )}
                            </div>
                            <p>{source.reason}</p>
                            {source.category === 'email' && (
                              <p>
                                Data freshness: {source.freshness}. Last
                                successful scan:{' '}
                                {source.last_success
                                  ? when(source.last_success)
                                  : 'Never observed'}
                                .
                              </p>
                            )}
                            {(source.scope ||
                              source.capabilities.length > 0) && (
                              <details className="power-source-details">
                                <summary>Scope and supported outcomes</summary>
                                {source.scope && (
                                  <p className="power-meta">{source.scope}</p>
                                )}
                                {source.capabilities.length > 0 && (
                                  <p>
                                    <strong>Supports:</strong>{' '}
                                    {source.capabilities.map(title).join(', ')}.
                                    Dependencies below determine availability.
                                  </p>
                                )}
                              </details>
                            )}
                            {source.state !== 'planned' && (
                              <div className="power-actions">
                                {source.last_run_id && onOpenScan && (
                                  <Button
                                    variant="outline"
                                    onClick={() =>
                                      onOpenScan(source.last_run_id!)
                                    }
                                  >
                                    Inspect last successful scan
                                  </Button>
                                )}
                                <Button
                                  variant="outline"
                                  onClick={() => action(source.action)}
                                >
                                  Open {source.action}
                                </Button>
                                <Button
                                  variant="ghost"
                                  disabled={busy}
                                  onClick={() => void load(source.title)}
                                  aria-label={`Check ${source.title} locally`}
                                >
                                  Check locally
                                </Button>
                              </div>
                            )}
                          </CardContent>
                        </Card>
                      )
                    })}
                </div>
                {snapshot.sources.filter(
                  (s) =>
                    (category === 'all' || s.category === category) &&
                    (connectionFilter === 'all' ||
                      s.configured === (connectionFilter === 'connected')),
                ).length === 0 && <p>No sources match these filters.</p>}
              </section>
              <section aria-labelledby="power-health">
                <h2 id="power-health">
                  <Activity aria-hidden="true" size={21} /> Health and next
                  actions
                </h2>
                <p className="power-meta">
                  Activity period: {when(snapshot.period_start)} –{' '}
                  {when(snapshot.checked_at)}. Local workspace is excluded from
                  connected-source counts.
                </p>
                <p>
                  AI requests: {snapshot.ai_requests}/{snapshot.ai_limit};
                  resets {when(snapshot.ai_resets_at)}.{' '}
                  {snapshot.paused_schedules} intentionally paused schedule(s);
                  paused is not failed.
                </p>
                {snapshot.issues_truncated && (
                  <p role="alert">
                    Some diagnostics exceed the bounded overview. Inspect
                    Settings and Scans for the complete lists.
                  </p>
                )}
                {snapshot.issues.length === 0 ? (
                  <p>
                    No actionable local issues detected. External services may
                    still be unverified.
                  </p>
                ) : (
                  <ul className="power-issues">
                    {[...snapshot.issues]
                      .sort(
                        (a, b) =>
                          Number(b.state === 'failed') -
                          Number(a.state === 'failed'),
                      )
                      .map((issue) => (
                        <li key={issue.id}>
                          <div>
                            <strong>{issue.title}</strong>
                            <StatePill
                              state={issue.state}
                              label={labels[issue.state]}
                            />
                            <p>{issue.reason}</p>
                          </div>
                          <Button
                            variant="outline"
                            onClick={() =>
                              issue.run_id && onOpenScan
                                ? onOpenScan(issue.run_id)
                                : action(issue.action)
                            }
                          >
                            {issue.run_id
                              ? 'Inspect scan'
                              : `Open ${issue.action}`}
                            <ArrowUpRight aria-hidden="true" size={15} />
                          </Button>
                        </li>
                      ))}
                  </ul>
                )}
              </section>
            </>
          )}
          <section
            aria-labelledby={compact ? 'connection-outcomes' : 'power-outcomes'}
          >
            <h2 id={compact ? 'connection-outcomes' : 'power-outcomes'}>
              {compact
                ? 'Available and still needs setup'
                : 'Capability breakdown'}
            </h2>
            <p>
              Each outcome counts once. Extra providers do not add duplicate
              points. Unverified dependencies leave the total incomplete.
            </p>
            {compact && (
              <>
                <p>
                  <strong>Already available:</strong>{' '}
                  {snapshot.capabilities
                    .filter(
                      (c) =>
                        c.available_to_request &&
                        !changes?.newly.includes(c.id),
                    )
                    .map((c) => c.title)
                    .join(', ') || 'None established yet'}
                  .
                </p>
                <p>
                  <strong>Still needs setup:</strong>{' '}
                  {snapshot.capabilities
                    .filter((c) => !c.available_to_request)
                    .map((c) => c.title)
                    .join(', ') || 'No configuration blockers'}
                  . Health remains separate from configuration.
                </p>
              </>
            )}
            <details open={compact ? undefined : true}>
              <summary>
                {compact
                  ? 'View capability prerequisites and next actions'
                  : 'Readiness details'}
              </summary>
              <div className="power-capabilities">
                {snapshot.capabilities.map((c) => {
                  const [icon, tone] = capabilityLook(c.id)
                  return (
                    <div
                      className="power-capability"
                      key={c.id}
                      data-tone={tone}
                    >
                      <div>
                        <ToneIcon icon={icon} tone={tone} size={16} />
                        <h3>{c.title}</h3>
                        <StatePill
                          state={stale ? 'stale' : c.state}
                          label={stale ? 'Stale snapshot' : labels[c.state]}
                        />
                        {!compact && <span>{c.weight} points</span>}
                      </div>
                      <p>{c.reason}</p>
                      <Button variant="link" onClick={() => action(c.action)}>
                        Open {c.action}
                        <ArrowUpRight aria-hidden="true" size={15} />
                      </Button>
                    </div>
                  )
                })}
              </div>
            </details>
            {onOpenAssistant && (
              <Button variant="outline" onClick={onOpenAssistant}>
                Open Chat to choose a model or ask a question
              </Button>
            )}
          </section>
          {!compact && (
            <details className="power-explanation">
              <summary>
                <CircleHelp size={17} aria-hidden="true" /> How readiness and
                health work
              </summary>
              <p>
                Catalog 1 totals 100 points: local evidence 20, inventory 15,
                maintenance 10, downloads 10, AI answers 15, photo reading 10,
                Gmail text 10 and purchase discovery 10. Only Ready outcomes
                earn confirmed points. Unknown or stale outcomes contribute to
                the possible upper bound; blocked, disabled and failed outcomes
                earn zero. Planned sources are excluded.
              </p>
              <p>
                Gmail processing observations expire after 24 hours; data is
                labelled stale after 7 days. Successful work covers only its
                requested query and date window. A reconnect invalidates earlier
                grant observations. AI/model reachability cannot be established
                from saved credentials or aggregate usage, so remains
                unverified. A cancelled run is not a provider failure. Failed
                runs from the last 7 days remain available for inspection even
                after recovery.
              </p>
              <p>
                No recurring external probes, folder watcher, automatic model
                switching or worker restart is performed. Requested AI work may
                cost money under your configured provider. New connections never
                start ingestion.
              </p>
            </details>
          )}
        </>
      )}
    </section>
  )
}
