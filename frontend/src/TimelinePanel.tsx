import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Boxes,
  CalendarClock,
  Camera,
  ChevronLeft,
  ChevronRight,
  FileText,
  Receipt,
  ShoppingBag,
  TriangleAlert,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ToneIcon, type Tone } from './tones'
import './timeline.css'

export type EventKind =
  | 'purchase'
  | 'order'
  | 'maintenance_done'
  | 'maintenance_due'
  | 'asset'
  | 'document'
  | 'photo'

export type TimelineTarget = {
  view:
    'Assets' | 'Profiles' | 'Memories' | 'Documents' | 'Photos' | 'Purchases'
  id: string
}

type Spending = {
  currency: string
  total_minor: number
  line_count: number
  by_month: number[]
  undated_minor: number
  undated_count: number
  largest: {
    receipt_id: string
    index: number
    source_id: string
    name: string
    total_minor: number
    purchase_date: string
  }[]
}

export type Dashboard = {
  months: string[]
  today: string
  spending: Spending[]
  missing_total_count: number
  activity: Record<
    'purchase' | 'asset' | 'document' | 'photo' | 'maintenance_done',
    number[]
  >
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
  truncated: boolean
}

type TimelineEvent = {
  id: string
  kind: EventKind
  date: string
  date_basis: 'stated' | 'recorded'
  title: string
  detail: string
  amount_minor: number | null
  currency: string | null
  target: TimelineTarget
}

type Month = { month: string; items: TimelineEvent[]; truncated: boolean }

const kinds: Record<
  EventKind,
  { label: string; icon: LucideIcon; tone: Tone; plural: string }
> = {
  purchase: {
    label: 'Bought',
    plural: 'Items bought',
    icon: Receipt,
    tone: 'finance',
  },
  order: {
    label: 'Order',
    plural: 'Order evidence',
    icon: ShoppingBag,
    tone: 'power',
  },
  maintenance_done: {
    label: 'Done',
    plural: 'Maintenance done',
    icon: Wrench,
    tone: 'maintenance',
  },
  maintenance_due: {
    label: 'Due',
    plural: 'Maintenance due',
    icon: CalendarClock,
    tone: 'maintenance',
  },
  asset: {
    label: 'Added',
    plural: 'Assets added',
    icon: Boxes,
    tone: 'assets',
  },
  document: {
    label: 'Document',
    plural: 'Documents',
    icon: FileText,
    tone: 'documents',
  },
  photo: { label: 'Photo', plural: 'Photos', icon: Camera, tone: 'photos' },
}

// Activity series in a fixed order, so a series keeps its color whatever is shown.
const activitySeries = [
  'purchase',
  'asset',
  'document',
  'photo',
  'maintenance_done',
] as const

const failedText = 'Unable to load your timeline.'
const EVENT_PREVIEW = 12

function timeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

function money(minor: number, currency: string): string {
  const digits = currency === 'JPY' ? 0 : 2
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(minor / 10 ** digits)
}

function monthName(key: string, style: 'short' | 'long' = 'short'): string {
  const [year, month] = key.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, 1)).toLocaleDateString(undefined, {
    month: style,
    year: style === 'long' ? 'numeric' : undefined,
    timeZone: 'UTC',
  })
}

function shiftMonth(key: string, by: number): string {
  const [year, month] = key.split('-').map(Number)
  const value = new Date(Date.UTC(year, month - 1 + by, 1))
  return `${value.getUTCFullYear()}-${String(value.getUTCMonth() + 1).padStart(2, '0')}`
}

function dayName(value: string): string {
  return new Date(`${value}T00:00:00Z`).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
}

async function read<T>(
  url: string,
  signal: AbortSignal,
  refreshSession?: () => Promise<void>,
): Promise<T> {
  const response = await fetch(url, {
    credentials: 'same-origin',
    cache: 'no-store',
    signal,
  })
  if (response.status === 401) await refreshSession?.()
  if (!response.ok) throw new Error(failedText)
  return (await response.json()) as T
}

type Series = { key: string; label: string; tone: Tone; values: number[] }

/** Month columns as buttons: hover or focus shows values, a click opens the month. */
function MonthBars({
  label,
  months,
  series,
  format,
  selected,
  onSelect,
}: {
  label: string
  months: string[]
  series: Series[]
  format: (value: number) => string
  selected: string
  onSelect: (month: string) => void
}) {
  const totals = months.map((_, index) =>
    series.reduce((sum, item) => sum + item.values[index], 0),
  )
  const peak = Math.max(...totals, 0)
  const every = months.length > 12 ? 3 : months.length > 6 ? 2 : 1
  return (
    <div className="month-bars" role="group" aria-label={label}>
      <div className="month-bars-scale" aria-hidden="true">
        <span>{peak ? format(peak) : ''}</span>
        <span>{peak ? format(peak / 2) : ''}</span>
        <span>{format(0)}</span>
      </div>
      <div className="month-bars-plot">
        {months.map((month, index) => {
          const parts = series.filter((item) => item.values[index] > 0)
          const description = `${monthName(month, 'long')}: ${
            series.length === 1
              ? format(totals[index])
              : series
                  .map((item) => `${item.label} ${format(item.values[index])}`)
                  .join(', ')
          }`
          return (
            <button
              key={month}
              type="button"
              className="month-bar"
              aria-pressed={selected === month}
              aria-label={description}
              onClick={() => onSelect(month)}
            >
              <span className="month-bar-track">
                <span
                  className="month-bar-stack"
                  style={{
                    height: peak ? `${(totals[index] / peak) * 100}%` : '0%',
                  }}
                >
                  {parts.map((item) => (
                    <span
                      key={item.key}
                      className="month-bar-part"
                      data-tone={item.tone}
                      style={{ flexGrow: item.values[index] }}
                    />
                  ))}
                </span>
              </span>
              <span className="month-bar-label" aria-hidden="true">
                {index % every === (months.length - 1) % every
                  ? monthName(month)
                  : ''}
              </span>
              <span className="month-bar-tip" aria-hidden="true">
                <strong>{monthName(month, 'long')}</strong>
                {series.length === 1 ? (
                  <span>{format(totals[index])}</span>
                ) : (
                  series.map((item) => (
                    <span key={item.key} className="tip-row">
                      <i data-tone={item.tone} />
                      {item.label}
                      <b>{format(item.values[index])}</b>
                    </span>
                  ))
                )}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

export function TimelinePanel({
  refreshSession,
  onOpen,
}: {
  refreshSession?: () => Promise<void>
  onOpen: (target: TimelineTarget) => void
}) {
  const zone = useMemo(() => timeZone(), [])
  const [range, setRange] = useState<6 | 12 | 24>(12)
  const [dashboard, setDashboard] = useState<Dashboard | null>(null)
  const [dashboardError, setDashboardError] = useState('')
  const [currency, setCurrency] = useState('')
  const [month, setMonth] = useState('')
  const [events, setEvents] = useState<Month | null>(null)
  const [eventsError, setEventsError] = useState('')
  const [hidden, setHidden] = useState<EventKind[]>([])
  // A busy month shows its first events; the rest open on request.
  const [expandedMonth, setExpandedMonth] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    read<Dashboard>(
      `/api/insights/dashboard?months=${range}&timezone=${encodeURIComponent(zone)}`,
      controller.signal,
      refreshSession,
    )
      .then((data) => {
        setDashboard(data)
        setDashboardError('')
        setMonth((current) => current || data.months[data.months.length - 1])
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return
        setDashboardError(
          caught instanceof Error && caught.name !== 'AbortError'
            ? caught.message
            : failedText,
        )
      })
    return () => controller.abort()
  }, [range, zone, refreshSession])

  const loadMonth = useCallback(
    (key: string, signal: AbortSignal) => {
      return read<Month>(
        `/api/insights/timeline?month=${key}&timezone=${encodeURIComponent(zone)}`,
        signal,
        refreshSession,
      )
        .then((data) => {
          setEvents(data)
          setEventsError('')
        })
        .catch((caught: unknown) => {
          if (signal.aborted) return
          setEventsError(
            caught instanceof Error && caught.name !== 'AbortError'
              ? caught.message
              : failedText,
          )
        })
    },
    [zone, refreshSession],
  )
  useEffect(() => {
    if (!month) return
    const controller = new AbortController()
    void loadMonth(month, controller.signal)
    return () => controller.abort()
  }, [month, loadMonth])

  const spending =
    dashboard?.spending.find((item) => item.currency === currency) ??
    dashboard?.spending[0]
  const sum = (values: number[] = []) => values.reduce((a, b) => a + b, 0)
  const added = dashboard
    ? sum(dashboard.activity.asset) +
      sum(dashboard.activity.document) +
      sum(dashboard.activity.photo)
    : 0
  const latest = dashboard?.months[dashboard.months.length - 1] ?? ''
  const shown = (events?.items ?? []).filter(
    (item) => !hidden.includes(item.kind),
  )
  const visible =
    expandedMonth === month ? shown : shown.slice(0, EVENT_PREVIEW)
  const present = [...new Set((events?.items ?? []).map((item) => item.kind))]
  const selectMonth = (key: string) => {
    setMonth(key)
    document
      .getElementById('timeline-month-heading')
      ?.scrollIntoView?.({ block: 'start', behavior: 'smooth' })
  }

  return (
    <section className="timeline-panel" aria-labelledby="timeline-heading">
      <div className="timeline-head">
        <div>
          <h1 id="timeline-heading">Timeline</h1>
          <p>
            What you bought, added and looked after, month by month. Built only
            from your saved records and their sources.
          </p>
        </div>
        <div className="timeline-range" role="group" aria-label="Time range">
          {([6, 12, 24] as const).map((value) => (
            <Button
              key={value}
              size="sm"
              variant={range === value ? 'default' : 'outline'}
              aria-pressed={range === value}
              onClick={() => setRange(value)}
            >
              {value} months
            </Button>
          ))}
        </div>
      </div>

      {dashboardError ? (
        <p className="timeline-error" role="alert">
          {dashboardError}
        </p>
      ) : !dashboard ? (
        <p className="timeline-muted" role="status">
          Loading your timeline…
        </p>
      ) : (
        <>
          <div className="timeline-stats">
            <div className="timeline-stat" data-tone="finance">
              <ToneIcon icon={Receipt} tone="finance" size={18} />
              <span>Spent, last {range} months</span>
              <strong>
                {spending
                  ? money(spending.total_minor, spending.currency)
                  : 'No totals yet'}
              </strong>
            </div>
            <div className="timeline-stat">
              <ToneIcon icon={ShoppingBag} tone="finance" size={18} />
              <span>Items bought</span>
              <strong>{sum(dashboard.activity.purchase)}</strong>
            </div>
            <div className="timeline-stat">
              <ToneIcon icon={Boxes} tone="assets" size={18} />
              <span>Things saved</span>
              <strong>{added}</strong>
            </div>
            <div className="timeline-stat">
              <ToneIcon icon={Wrench} tone="maintenance" size={18} />
              <span>Maintenance done</span>
              <strong>{sum(dashboard.activity.maintenance_done)}</strong>
            </div>
          </div>

          <div className="timeline-grid">
            <article className="timeline-card" aria-labelledby="money-heading">
              <div className="timeline-card-head">
                <h2 id="money-heading">Spending by month</h2>
                {dashboard.spending.length > 1 ? (
                  <div
                    className="timeline-range"
                    role="group"
                    aria-label="Currency"
                  >
                    {dashboard.spending.map((item) => (
                      <Button
                        key={item.currency}
                        size="sm"
                        variant={
                          item.currency === spending?.currency
                            ? 'default'
                            : 'outline'
                        }
                        aria-pressed={item.currency === spending?.currency}
                        onClick={() => setCurrency(item.currency)}
                      >
                        {item.currency}
                      </Button>
                    ))}
                  </div>
                ) : null}
              </div>
              {spending ? (
                <>
                  <MonthBars
                    label={`Spending by month in ${spending.currency}`}
                    months={dashboard.months}
                    series={[
                      {
                        key: 'spent',
                        label: 'Spent',
                        tone: 'finance',
                        values: spending.by_month,
                      },
                    ]}
                    format={(value) =>
                      money(Math.round(value), spending.currency)
                    }
                    selected={month}
                    onSelect={selectMonth}
                  />
                  {spending.largest.length ? (
                    <>
                      <h3>Largest purchases</h3>
                      <ol className="timeline-largest">
                        {spending.largest.map((line) => (
                          <li key={`${line.receipt_id}:${line.index}`}>
                            <button
                              type="button"
                              className="timeline-link"
                              onClick={() =>
                                onOpen({ view: 'Memories', id: line.source_id })
                              }
                            >
                              {line.name}
                            </button>
                            <span className="timeline-muted">
                              {dayName(line.purchase_date)}
                            </span>
                            <strong>
                              {money(line.total_minor, spending.currency)}
                            </strong>
                          </li>
                        ))}
                      </ol>
                    </>
                  ) : null}
                </>
              ) : (
                <p className="empty-state">
                  No purchase totals yet. Confirm a receipt and record its line
                  total and purchase date to see spending here.
                </p>
              )}
              <p className="timeline-note">
                Adds up the line totals you confirmed on receipts, in their own
                currency. Order totals on Purchases are not added again.
                {spending?.undated_count
                  ? ` ${spending.undated_count} total${spending.undated_count === 1 ? '' : 's'} (${money(spending.undated_minor, spending.currency)}) ${spending.undated_count === 1 ? 'has' : 'have'} no purchase date, so no month.`
                  : ''}
                {dashboard.missing_total_count
                  ? ` ${dashboard.missing_total_count} item${dashboard.missing_total_count === 1 ? '' : 's'} bought in this range ${dashboard.missing_total_count === 1 ? 'has' : 'have'} no total yet.`
                  : ''}
              </p>
            </article>

            <article
              className="timeline-card"
              aria-labelledby="activity-heading"
            >
              <div className="timeline-card-head">
                <h2 id="activity-heading">Activity by month</h2>
              </div>
              <MonthBars
                label="Activity by month"
                months={dashboard.months}
                series={activitySeries.map((key) => ({
                  key,
                  label: kinds[key].plural,
                  tone: kinds[key].tone,
                  values: dashboard.activity[key],
                }))}
                format={(value) => String(Math.round(value))}
                selected={month}
                onSelect={selectMonth}
              />
              <ul className="timeline-legend" aria-label="Legend">
                {activitySeries.map((key) => (
                  <li key={key}>
                    <i data-tone={kinds[key].tone} aria-hidden="true" />
                    {kinds[key].plural}
                    <b>{sum(dashboard.activity[key])}</b>
                  </li>
                ))}
              </ul>
              <details className="timeline-table">
                <summary>Show as a table</summary>
                <div className="timeline-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th scope="col">Month</th>
                        {activitySeries.map((key) => (
                          <th key={key} scope="col">
                            {kinds[key].plural}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {dashboard.months.map((key, index) => (
                        <tr key={key}>
                          <th scope="row">{monthName(key, 'long')}</th>
                          {activitySeries.map((series) => (
                            <td key={series}>
                              {dashboard.activity[series][index]}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            </article>
          </div>

          <article className="timeline-card" aria-labelledby="upcoming-heading">
            <div className="timeline-card-head">
              <h2 id="upcoming-heading">Coming up</h2>
              {dashboard.overdue_count ? (
                <Badge variant="destructive">
                  <TriangleAlert aria-hidden="true" size={13} />
                  {dashboard.overdue_count} overdue
                </Badge>
              ) : null}
            </div>
            {dashboard.upcoming.length ? (
              <ul className="timeline-upcoming">
                {dashboard.upcoming.map((task) => (
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
                      className="timeline-link"
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
                    <span className="timeline-muted">{task.entity_name}</span>
                    <span className="timeline-due">
                      {task.overdue ? 'Overdue · ' : 'Due '}
                      {dayName(task.due_on)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="timeline-muted">Nothing due in the next 30 days.</p>
            )}
          </article>
          {dashboard.truncated ? (
            <p className="timeline-note">
              You have more receipt lines than one view reads; older ones may be
              missing from these totals.
            </p>
          ) : null}
        </>
      )}

      {month ? (
        <article
          className="timeline-card"
          aria-labelledby="timeline-month-heading"
        >
          <div className="timeline-card-head">
            <h2 id="timeline-month-heading">{monthName(month, 'long')}</h2>
            <div className="timeline-range">
              <Button
                size="sm"
                variant="outline"
                aria-label="Previous month"
                onClick={() => setMonth(shiftMonth(month, -1))}
              >
                <ChevronLeft aria-hidden="true" size={16} />
              </Button>
              <Button
                size="sm"
                variant="outline"
                aria-label="Next month"
                disabled={month >= latest}
                onClick={() => setMonth(shiftMonth(month, 1))}
              >
                <ChevronRight aria-hidden="true" size={16} />
              </Button>
            </div>
          </div>
          {present.length > 1 ? (
            <div className="timeline-filters" role="group" aria-label="Show">
              {present.map((kind) => (
                <Button
                  key={kind}
                  size="sm"
                  variant="outline"
                  className="timeline-filter"
                  data-tone={kinds[kind].tone}
                  aria-pressed={!hidden.includes(kind)}
                  onClick={() =>
                    setHidden((current) =>
                      current.includes(kind)
                        ? current.filter((item) => item !== kind)
                        : [...current, kind],
                    )
                  }
                >
                  {kinds[kind].plural}
                </Button>
              ))}
            </div>
          ) : null}
          {eventsError ? (
            <p className="timeline-error" role="alert">
              {eventsError}
            </p>
          ) : !events || events.month !== month ? (
            <p className="timeline-muted" role="status">
              Loading {monthName(month, 'long')}…
            </p>
          ) : shown.length ? (
            <ol className="timeline-events">
              {visible.map((item, index) => {
                const kind = kinds[item.kind]
                const firstOfDay =
                  index === 0 || visible[index - 1].date !== item.date
                return (
                  <li key={item.id} className="timeline-event">
                    <span className="timeline-day" aria-hidden={!firstOfDay}>
                      {firstOfDay ? dayName(item.date) : ''}
                    </span>
                    <span className="timeline-dot" data-tone={kind.tone}>
                      <kind.icon aria-hidden="true" size={15} />
                    </span>
                    <button
                      type="button"
                      className="timeline-event-card"
                      onClick={() => onOpen(item.target)}
                    >
                      <span className="timeline-event-main">
                        <strong>{item.title}</strong>
                        <span className="timeline-muted">
                          {[kind.label, item.detail]
                            .filter(Boolean)
                            .join(' · ')}
                          {item.date_basis === 'recorded'
                            ? ' · saved in LifeGather'
                            : ''}
                        </span>
                      </span>
                      {item.amount_minor !== null && item.currency ? (
                        <span className="timeline-amount">
                          {money(item.amount_minor, item.currency)}
                        </span>
                      ) : null}
                    </button>
                  </li>
                )
              })}
              {visible.length < shown.length ? (
                <li className="timeline-more">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setExpandedMonth(month)}
                  >
                    Show all {shown.length} events
                  </Button>
                </li>
              ) : null}
            </ol>
          ) : (
            <p className="empty-state">
              Nothing recorded in {monthName(month, 'long')}.
            </p>
          )}
          {events?.truncated ? (
            <p className="timeline-note">
              This month has more events than one view shows.
            </p>
          ) : null}
        </article>
      ) : null}
    </section>
  )
}
