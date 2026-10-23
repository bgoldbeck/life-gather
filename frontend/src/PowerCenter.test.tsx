import { act, render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { PowerCenter, type PowerSnapshot } from './PowerCenter'

const now = Math.floor(Date.now() / 1000)
function snapshot(): PowerSnapshot {
  return {
    checked_at: now,
    expires_at: now + 300,
    scoring_version: '1',
    score: null,
    minimum_score: 55,
    maximum_score: 65,
    capabilities: [
      {
        id: 'local',
        title: 'Local evidence',
        weight: 55,
        state: 'ready',
        reason: 'Works without AI.',
        action: 'Documents',
        available_to_request: true,
      },
      {
        id: 'gmail_import',
        title: 'Gmail evidence',
        weight: 10,
        state: 'unknown',
        reason: 'No successful scan yet.',
        action: 'Scans',
        available_to_request: true,
      },
      {
        id: 'ai',
        title: 'AI answers',
        weight: 35,
        state: 'blocked',
        reason: 'Configure AI and permission.',
        action: 'Settings',
        available_to_request: false,
      },
    ],
    sources: [
      {
        id: 'local',
        title: 'Workspace',
        category: 'local',
        configured: true,
        state: 'ready',
        reason: 'Local only',
        capabilities: ['local'],
        action: 'Documents',
        last_success: null,
        freshness: 'unknown',
        scope: 'Manual uploads',
      },
      {
        id: 'gmail',
        title: 'Synthetic mailbox',
        category: 'email',
        configured: true,
        state: 'unknown',
        reason: 'Grant not yet checked by a scan',
        capabilities: ['gmail_import'],
        action: 'Scans',
        last_success: null,
        freshness: 'unknown',
        scope: 'Read-only',
      },
      {
        id: 'bank',
        title: 'Bank syncing',
        category: 'planned',
        configured: false,
        state: 'planned',
        reason: 'Planned feature',
        capabilities: [],
        action: 'Settings',
        last_success: null,
        freshness: 'unknown',
        scope: '',
      },
    ],
    issues: [
      {
        id: 'failed',
        title: 'Failed synthetic scan',
        reason: 'Inspect and retry.',
        action: 'Scans',
        state: 'failed',
        run_id: 'run-1',
      },
    ],
    issues_truncated: false,
    connected_sources: 1,
    completed_scans_7d: 2,
    imported_messages_7d: 4,
    period_start: now - 7 * 86400,
    ai_requests: 3,
    ai_limit: 20,
    ai_resets_at: now + 86400,
    paused_schedules: 1,
  }
}
beforeEach(() => sessionStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

it('explains incomplete readiness, real activity and exact recovery navigation', async () => {
  const fetcher = vi.fn(async () => Response.json(snapshot()))
  vi.stubGlobal('fetch', fetcher)
  const open = vi.fn()
  render(<PowerCenter userId="alice" onNavigate={vi.fn()} onOpenScan={open} />)
  expect(await screen.findByText('Incomplete')).toBeVisible()
  expect(
    screen.getByText(
      '55 confirmed points; up to 65 if unverified/stale dependencies work.',
    ),
  ).toBeVisible()
  expect(screen.getByText(/4 newly imported messages/)).toBeVisible()
  expect(screen.getByText(/1 intentionally paused/)).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Inspect scan' }))
  expect(open).toHaveBeenCalledWith('run-1')
  expect(fetcher.mock.calls).toHaveLength(1)
  expect(fetcher.mock.calls[0]).toEqual([
    '/api/power',
    expect.objectContaining({ cache: 'no-store', credentials: 'same-origin' }),
  ])
})

it('filters source cards and refreshes observations without claiming provider verification', async () => {
  const fetcher = vi.fn(async () => Response.json(snapshot()))
  vi.stubGlobal('fetch', fetcher)
  render(<PowerCenter userId="alice" onNavigate={vi.fn()} />)
  await screen.findByText('Incomplete')
  await userEvent.selectOptions(
    screen.getByLabelText('Source category'),
    'email',
  )
  expect(
    screen.queryByRole('heading', { name: 'Workspace' }),
  ).not.toBeInTheDocument()
  expect(
    screen.getByRole('heading', { name: 'Synthetic mailbox' }),
  ).toBeVisible()
  await userEvent.click(
    screen.getByRole('button', { name: 'Check Synthetic mailbox locally' }),
  )
  expect(
    await screen.findByText(
      /Local observations refreshed for Synthetic mailbox/,
    ),
  ).toBeVisible()
  expect(fetcher).toHaveBeenCalledTimes(2)
  await userEvent.selectOptions(
    screen.getByLabelText('Connection status'),
    'not-connected',
  )
  expect(screen.getByText('No sources match these filters.')).toBeVisible()
})

it('shows gained/lost capabilities per account and separates availability from discoveries', async () => {
  sessionStorage.setItem(
    'lifegather.power.capabilities.v1.alice',
    JSON.stringify(['local', 'ai']),
  )
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => Response.json(snapshot())),
  )
  render(<PowerCenter compact userId="alice" onNavigate={vi.fn()} />)
  await screen.findByText('Capabilities changed')
  const changes = screen.getByRole('status')
  expect(changes).toHaveTextContent('Gmail evidence')
  expect(changes).toHaveTextContent('No longer available: AI answers')
  expect(changes).toHaveTextContent(
    'Availability does not mean a discovery or scan has happened.',
  )
  expect(
    sessionStorage.getItem('lifegather.power.capabilities.v1.bob'),
  ).toBeNull()
  await userEvent.click(
    screen.getByRole('button', { name: 'Dismiss capability changes' }),
  )
  expect(screen.queryByText('Capabilities changed')).not.toBeInTheDocument()
})

it('preserves prior status on refresh failure, labels stale snapshots and supports retry', async () => {
  const value = snapshot()
  value.expires_at = now - 1
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json(value))
    .mockResolvedValueOnce(new Response('', { status: 503 }))
    .mockResolvedValueOnce(Response.json(snapshot()))
  vi.stubGlobal('fetch', fetcher)
  render(<PowerCenter userId="alice" onNavigate={vi.fn()} />)
  expect(
    await screen.findByText('Snapshot expired; status is stale.'),
  ).toBeVisible()
  await userEvent.click(
    screen.getByRole('button', { name: 'Check all locally' }),
  )
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Power Center is unavailable',
  )
  expect(screen.getByText(/4 newly imported messages/)).toBeVisible()
  await userEvent.click(
    screen.getByRole('button', { name: 'Retry Power Center' }),
  )
  expect(await screen.findByText('Incomplete')).toBeVisible()
})

it('discards late old-account callbacks when the account changes', async () => {
  let finish!: (value: Response) => void
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            finish = resolve
          }),
      )
      .mockResolvedValueOnce(Response.json(snapshot())),
  )
  const view = render(<PowerCenter userId="alice" onNavigate={vi.fn()} />)
  await waitFor(() => expect(finish).toBeTypeOf('function'))
  view.rerender(<PowerCenter userId="bob" onNavigate={vi.fn()} />)
  await screen.findByText('Incomplete')
  const old = snapshot()
  old.score = 99
  await act(async () => finish(Response.json(old)))
  expect(screen.queryByText('99%')).not.toBeInTheDocument()
  expect(
    sessionStorage.getItem('lifegather.power.capabilities.v1.alice'),
  ).toBeNull()
})

it('automatic checks remain local and refresh on configuration changes', async () => {
  const fetcher = vi.fn(async () => Response.json(snapshot()))
  vi.stubGlobal('fetch', fetcher)
  const view = render(
    <PowerCenter userId="alice" changeSignal={0} onNavigate={vi.fn()} />,
  )
  await screen.findByText('Incomplete')
  view.rerender(
    <PowerCenter userId="alice" changeSignal={1} onNavigate={vi.fn()} />,
  )
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2))
  vi.useFakeTimers()
  view.rerender(
    <PowerCenter userId="alice" changeSignal={2} onNavigate={vi.fn()} />,
  )
  await act(async () => {})
  await act(async () => vi.advanceTimersByTimeAsync(60000))
  expect(fetcher).toHaveBeenCalledTimes(4)
  expect(
    within(screen.getByRole('region', { name: 'Power Center' })).getByText(
      'Incomplete',
    ),
  ).toBeVisible()
})

it('shows the growth power bar from reported points only', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => Response.json(snapshot())),
  )
  render(<PowerCenter userId="alice" onNavigate={vi.fn()} />)
  const meter = await screen.findByRole('meter', { name: 'Power level' })
  expect(meter).toHaveAttribute('aria-valuenow', '55')
  expect(meter).toHaveAttribute(
    'aria-valuetext',
    '55 confirmed points, up to 65 if unverified dependencies work; stage Growing',
  )
  expect(screen.getByText('55–65 pts')).toBeVisible()
  expect(
    screen.getByRole('heading', { name: 'Synthetic mailbox' }).parentElement,
  ).toHaveTextContent('Unverified')
})

it('lists connections before health and folds each source scope into details', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => Response.json(snapshot())),
  )
  render(<PowerCenter userId="alice" onNavigate={vi.fn()} />)
  const connections = await screen.findByRole('heading', {
    name: 'Your connections',
  })
  const health = screen.getByRole('heading', {
    name: 'Health and next actions',
  })
  expect(
    connections.compareDocumentPosition(health) &
      Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy()
  const scope = screen.getByText('Read-only')
  expect(scope.closest('details')).not.toHaveAttribute('open')
  expect(scope.closest('details')).toHaveTextContent(
    'Scope and supported outcomes',
  )
})
