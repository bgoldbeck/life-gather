import { useCallback, useEffect, useState, type CSSProperties } from 'react'
import {
  ArrowUpRight,
  BookOpen,
  Boxes,
  CalendarClock,
  Camera,
  ChartColumn,
  CircleCheck,
  ClipboardCheck,
  FileText,
  MessageCircle,
  MessageSquare,
  Network,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  type LucideIcon,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ToneIcon, type Tone } from './tones'
import { navItem } from './navigation'
import './overview.css'

export type OverviewPage =
  | 'Assets'
  | 'Documents'
  | 'Photos'
  | 'Memories'
  | 'Profiles'
  | 'Review'
  | 'Graph'
  | 'Timeline'
  | 'Maintenance'

type Target = { view: OverviewPage; id: string }

export type Overview = {
  today: string
  counts: {
    assets: number
    documents: number
    photos: number
    memories: number
  }
  review_count: number
  overdue_count: number
  upcoming: {
    task_id: string
    title: string
    due_on: string
    overdue: boolean
    entity_id: string
    entity_name: string
    entity_kind: string
  }[]
  recent: {
    kind: 'asset' | 'document' | 'photo'
    title: string
    recorded_at: number
    target: Target
  }[]
}

const failedText = 'Unable to load your overview.'
const UPCOMING_PREVIEW = 4

function timeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

function dayName(value: string): string {
  return new Date(`${value}T00:00:00Z`).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
}

// Saved times are microseconds; "today" comes from the server in the browser's zone.
function savedWhen(micros: number, today: string): string {
  const saved = new Date(micros / 1000)
  const local = (value: Date) =>
    `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
  const day = local(saved)
  if (day === today) return 'Today'
  const yesterday = new Date(`${today}T12:00:00`)
  yesterday.setDate(yesterday.getDate() - 1)
  if (day === local(yesterday)) return 'Yesterday'
  return saved.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

const tiles: {
  key: keyof Overview['counts']
  label: string
  icon: LucideIcon
  tone: Tone
  view: OverviewPage
}[] = [
  {
    key: 'assets',
    label: 'Assets',
    icon: Boxes,
    tone: 'assets',
    view: 'Assets',
  },
  {
    key: 'documents',
    label: 'Documents',
    icon: FileText,
    tone: 'documents',
    view: 'Documents',
  },
  {
    key: 'photos',
    label: 'Photos',
    icon: Camera,
    tone: 'photos',
    view: 'Photos',
  },
  {
    key: 'memories',
    label: 'Memories',
    icon: BookOpen,
    tone: 'ai',
    view: 'Memories',
  },
]

const recentKinds: Record<
  Overview['recent'][number]['kind'],
  { icon: LucideIcon; tone: Tone; label: string }
> = {
  asset: { icon: Boxes, tone: 'assets', label: 'Asset' },
  document: { icon: FileText, tone: 'documents', label: 'Document' },
  photo: { icon: Camera, tone: 'photos', label: 'Photo' },
}

// Pages around the centre, clockwise from the top left. Their icons and tones
// come from the main menu, so the hero always matches it.
const orbitPages = [
  'Memories',
  'Timeline',
  'Assets',
  'Documents',
  'Chat',
  'Photos',
  'Maintenance',
] as const satisfies readonly (OverviewPage | 'Chat')[]
const tilts = [-9, 6, 8, -6, 7, -8, 5]

/** Where node `index` sits, in percent of the illustration: alternate nodes
 * ride the outer and inner orbit so the ring has depth. */
function place(index: number) {
  const angle = ((-125 + (360 / orbitPages.length) * index) * Math.PI) / 180
  const [rx, ry] = index % 2 === 0 ? [40, 40] : [30, 35]
  return { x: 50 + rx * Math.cos(angle), y: 45 + ry * Math.sin(angle) }
}

/** Hero illustration whose icons are links: a label shows on hover and focus. */
function Orbit({
  onNavigate,
  onOpenAssistant,
}: {
  onNavigate: (view: OverviewPage) => void
  onOpenAssistant: () => void
}) {
  const [active, setActive] = useState('')
  const graph = navItem('Graph')
  const nodes = orbitPages.map((page, index) => {
    // Chat is the assistant dock, not a menu page: use the dock's icon.
    const { icon, tone } =
      page === 'Chat'
        ? { icon: MessageSquare, tone: 'ai' as Tone }
        : navItem(page)
    return {
      page,
      icon,
      tone,
      tilt: tilts[index % tilts.length],
      ...place(index),
      open: page === 'Chat' ? onOpenAssistant : () => onNavigate(page),
    }
  })
  const highlight = (page: string) => ({
    onMouseEnter: () => setActive(page),
    onMouseLeave: () => setActive(''),
    onFocus: () => setActive(page),
    onBlur: () => setActive(''),
  })
  return (
    <nav className="memory-illustration" aria-label="Explore your workspace">
      <div className="orbit orbit-one" aria-hidden="true" />
      <div className="orbit orbit-two" aria-hidden="true" />
      <svg
        className="orbit-links"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        {nodes.map(({ page, tone, x, y }) => (
          <line
            key={page}
            x1={50}
            y1={45}
            x2={x}
            y2={y}
            data-tone={tone}
            data-active={active === page || active === 'Graph' || undefined}
          />
        ))}
      </svg>
      <button
        type="button"
        className="graph-center"
        data-tone={graph.tone}
        aria-label="Open Graph"
        onClick={() => onNavigate('Graph')}
        {...highlight('Graph')}
      >
        <graph.icon aria-hidden="true" size={44} strokeWidth={1.4} />
        <span className="orbit-label" aria-hidden="true">
          Graph
        </span>
      </button>
      {nodes.map(({ page, icon: Icon, tone, tilt, x, y, open }, index) => (
        <button
          key={page}
          type="button"
          className="graph-node"
          data-tone={tone}
          style={
            {
              left: `${x}%`,
              top: `${y}%`,
              '--tilt': `${tilt}deg`,
              '--delay': `${index * -0.9}s`,
            } as CSSProperties
          }
          aria-label={`Open ${page}`}
          onClick={open}
          {...highlight(page)}
        >
          <Icon aria-hidden="true" size={22} />
          <span className="orbit-label" aria-hidden="true">
            {page}
          </span>
        </button>
      ))}
      <span className="little-node little-one" aria-hidden="true" />
      <span className="little-node little-two" aria-hidden="true" />
      <span className="illustration-caption" aria-hidden="true">
        Every detail has a connection.
      </span>
    </nav>
  )
}

export function OverviewPanel({
  onNavigate,
  onOpen,
  onOpenAssistant,
  refreshSession,
}: {
  onNavigate: (view: OverviewPage) => void
  onOpen: (target: Target) => void
  onOpenAssistant: () => void
  refreshSession?: () => Promise<void>
}) {
  const [overview, setOverview] = useState<Overview | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const retry = useCallback(() => {
    setError('')
    setAttempt((value) => value + 1)
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    fetch(`/api/insights/overview?timezone=${encodeURIComponent(timeZone())}`, {
      credentials: 'same-origin',
      cache: 'no-store',
      signal: controller.signal,
    })
      .then(async (response) => {
        if (response.status === 401) await refreshSession?.()
        if (!response.ok) throw new Error(failedText)
        const data = (await response.json()) as Overview | null
        if (
          !data?.counts ||
          !Array.isArray(data.upcoming) ||
          !Array.isArray(data.recent)
        )
          throw new Error(failedText)
        return data
      })
      .then((data) => {
        if (!controller.signal.aborted) setOverview(data)
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(failedText)
      })
    return () => controller.abort()
  }, [attempt, refreshSession])

  const total = overview
    ? Object.values(overview.counts).reduce((sum, value) => sum + value, 0)
    : 0
  const soon = overview?.upcoming.filter((task) => !task.overdue).length ?? 0
  const waiting = overview
    ? overview.review_count + overview.overdue_count + soon
    : 0
  const more = overview
    ? overview.overdue_count + soon > UPCOMING_PREVIEW
    : false

  return (
    <>
      <div className="section-label">
        <span /> A HOME FOR WHAT MATTERS
      </div>
      <section className="welcome">
        <div className="welcome-copy">
          <h1>
            A little less <br />
            to remember.
          </h1>
          <p>
            Life is full of details. Give them a place to belong.
            <br className="desktop-break" /> Your things, stories, and
            connections — with their sources intact.
          </p>
          <Button className="explore-button" onClick={onOpenAssistant}>
            Explore your workspace <ArrowUpRight aria-hidden="true" size={17} />
          </Button>
          <span className="preview-note">
            Your account is ready. Save a memory or find it in Chat.
          </span>
        </div>
        <Orbit onNavigate={onNavigate} onOpenAssistant={onOpenAssistant} />
      </section>

      <section className="overview-glance" aria-labelledby="glance-heading">
        <div className="overview-heading">
          <h2 id="glance-heading">At a glance</h2>
          <Button
            variant="link"
            className="feature-link"
            onClick={() => onNavigate('Timeline')}
          >
            <ChartColumn aria-hidden="true" size={15} />
            Charts on the Timeline
          </Button>
        </div>
        {error ? (
          <div className="overview-error" role="alert">
            <span>{error}</span>
            <Button variant="outline" size="sm" onClick={retry}>
              <RefreshCw aria-hidden="true" size={14} /> Try again
            </Button>
          </div>
        ) : null}
        <div className="overview-tiles" aria-busy={!overview && !error}>
          {tiles.map(({ key, label, icon, tone, view }) => (
            <button
              key={key}
              type="button"
              className="overview-tile"
              onClick={() => onNavigate(view)}
            >
              <ToneIcon icon={icon} tone={tone} size={18} />
              <span>{label}</span>
              <strong>{overview ? overview.counts[key] : '–'}</strong>
            </button>
          ))}
        </div>
      </section>

      {overview ? (
        <div className="overview-columns">
          <section
            className="overview-card"
            aria-labelledby="attention-heading"
          >
            <div className="overview-heading">
              <h2 id="attention-heading">Needs your attention</h2>
              {waiting ? (
                <Badge variant="secondary">{waiting} waiting</Badge>
              ) : null}
            </div>
            {waiting ? (
              <ul className="overview-list">
                {overview.review_count ? (
                  <li>
                    <ToneIcon icon={ClipboardCheck} tone="power" size={16} />
                    <button
                      type="button"
                      className="overview-link"
                      onClick={() => onNavigate('Review')}
                    >
                      {overview.review_count === 1
                        ? '1 item to review'
                        : `${overview.review_count} items to review`}
                    </button>
                    <span className="overview-muted">
                      Details or matches LifeGather was unsure about
                    </span>
                  </li>
                ) : null}
                {overview.upcoming.slice(0, UPCOMING_PREVIEW).map((task) => (
                  <li
                    key={task.task_id}
                    data-overdue={task.overdue || undefined}
                  >
                    <ToneIcon
                      icon={CalendarClock}
                      tone="maintenance"
                      size={16}
                    />
                    <button
                      type="button"
                      className="overview-link"
                      onClick={() =>
                        onOpen({
                          view:
                            task.entity_kind === 'asset'
                              ? 'Assets'
                              : 'Profiles',
                          id: task.entity_id,
                        })
                      }
                    >
                      {task.title}
                    </button>
                    <span className="overview-muted">{task.entity_name}</span>
                    <span className="overview-when">
                      {task.overdue ? 'Overdue · ' : 'Due '}
                      {dayName(task.due_on)}
                    </span>
                  </li>
                ))}
                {more ? (
                  <li>
                    <button
                      type="button"
                      className="overview-link overview-more"
                      onClick={() => onNavigate('Timeline')}
                    >
                      See all maintenance on the Timeline
                    </button>
                  </li>
                ) : null}
              </ul>
            ) : (
              <p className="overview-calm">
                <CircleCheck aria-hidden="true" size={16} />
                You're all caught up. Nothing to review and no maintenance due
                in the next 30 days.
              </p>
            )}
          </section>

          <section className="overview-card" aria-labelledby="recent-heading">
            <div className="overview-heading">
              <h2 id="recent-heading">Recently added</h2>
            </div>
            {overview.recent.length ? (
              <ul className="overview-list">
                {overview.recent.map((item) => {
                  const kind = recentKinds[item.kind]
                  return (
                    <li key={`${item.kind}:${item.target.id}`}>
                      <ToneIcon icon={kind.icon} tone={kind.tone} size={16} />
                      <button
                        type="button"
                        className="overview-link"
                        onClick={() => onOpen(item.target)}
                      >
                        <span className="sr-only">{kind.label}: </span>
                        {item.title}
                      </button>
                      <span className="overview-when">
                        {savedWhen(item.recorded_at, overview.today)}
                      </span>
                    </li>
                  )
                })}
              </ul>
            ) : (
              <p className="overview-muted">
                Nothing saved yet. Add an asset, a document or a photo and it
                shows up here.
              </p>
            )}
          </section>
        </div>
      ) : null}

      {overview && total === 0 ? (
        <section className="start-section" aria-labelledby="start-heading">
          <div className="section-heading">
            <h2 id="start-heading">Your story starts here</h2>
          </div>
          <p className="section-description">
            A few good first steps for a new workspace.
          </p>
          <div className="feature-grid">
            {[
              {
                icon: MessageCircle,
                tone: 'ai' as Tone,
                title: 'Start with a conversation',
                text: 'A natural way to capture a detail or find something you remember.',
                open: onOpenAssistant,
                label: 'Explore Chat',
              },
              {
                icon: Boxes,
                tone: 'assets' as Tone,
                title: 'Keep the whole story',
                text: 'Connect your belongings to their receipts, repairs, and history.',
                open: () => onNavigate('Assets'),
                label: 'Explore Assets',
              },
              {
                icon: Network,
                tone: 'graph' as Tone,
                title: 'See how it connects',
                text: 'Follow the relationships between your memories, people, and places.',
                open: () => onNavigate('Graph'),
                label: 'Explore Graph',
              },
            ].map(({ icon: Icon, tone, title, text, open, label }) => (
              <Card key={title} className="feature-card">
                <CardContent>
                  <span className="feature-icon" data-tone={tone}>
                    <Icon aria-hidden="true" size={22} strokeWidth={1.5} />
                  </span>
                  <h3>{title}</h3>
                  <p>{text}</p>
                  <Button
                    variant="link"
                    className="feature-link"
                    onClick={open}
                  >
                    {label}
                    <ArrowUpRight aria-hidden="true" size={15} />
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      ) : null}

      <div className="principles">
        <ShieldCheck aria-hidden="true" size={23} />
        <div>
          <strong>Your memories deserve a source of truth.</strong>
          <p>
            Original evidence preserved. Uncertainty made clear. History kept
            intact.
          </p>
        </div>
        <span className="principles-icon">
          <CircleCheck aria-hidden="true" size={20} />
        </span>
      </div>
      <footer className="workspace-footer">
        Made for a life that keeps growing.
        <span>
          <Sparkles aria-hidden="true" size={13} /> LifeGather · Working name
        </span>
      </footer>
    </>
  )
}
