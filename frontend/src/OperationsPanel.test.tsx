import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Workspace } from './App'
import type { OperationsOverview } from './OperationsPanel'

afterEach(() => vi.unstubAllGlobals())

const overview: OperationsOverview = {
  checked_at: 1_792_500_000,
  background_mode: 'external',
  alerts: { webhook: true, email: false },
  jobs: {
    queued: 2,
    running: 1,
    completed_7d: 9,
    failed_7d: 3,
    canceled_7d: 0,
  },
  stuck: { expired_leases: 1, long_queued: 0, overdue_schedules: 2 },
  failures: [{ handler: 'gmail_import', count: 3, last_at: 1_792_499_000 }],
  schedules: { enabled: 4, paused: 1 },
  events: [
    {
      level: 'error',
      logger: 'lifegather.requests',
      message: 'Request failed unexpectedly',
      details: { route: '/api/assets/{asset_id}', error_type: 'ValueError' },
      count: 5,
      first_at: 1_792_400_000,
      last_at: 1_792_499_500,
      alerted_at: 1_792_400_000,
    },
  ],
  storage: {
    accounts: 2,
    photos: 3,
    documents: 1,
    photo_bytes: 3 * 1024 * 1024,
    document_bytes: 512 * 1024,
    total_bytes: 3 * 1024 * 1024 + 512 * 1024,
    largest: [
      {
        account: 'account-1a2b3c4d',
        photos: 3,
        documents: 1,
        bytes: 3_670_016,
      },
    ],
    quota_bytes: null,
  },
}

function stub(operator: boolean) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url === '/api/operator/access')
      return new Response(JSON.stringify({ operator }))
    if (url === '/api/operator/overview')
      return operator
        ? new Response(JSON.stringify(overview))
        : new Response('{}', { status: 404 })
    return new Response(JSON.stringify({ items: [], next_cursor: null }))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('Operations', () => {
  it('stays out of the navigation for other accounts', async () => {
    const fetchMock = stub(false)
    render(<Workspace userId="member" />)
    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/operator/access',
        expect.anything(),
      ),
    )
    const navigation = screen.getByRole('navigation', {
      name: 'Main navigation',
    })
    expect(
      within(navigation).queryByRole('button', { name: 'Operations' }),
    ).not.toBeInTheDocument()
  })

  it('shows operators job health, problems and storage as counts', async () => {
    const fetchMock = stub(true)
    const user = userEvent.setup()
    render(<Workspace userId="operator" />)
    await user.click(await screen.findByRole('button', { name: 'Operations' }))
    expect(
      screen.getByRole('heading', { level: 1, name: 'Operations' }),
    ).toBeVisible()
    expect(await screen.findByText('3 stuck')).toBeVisible()
    const stuck = screen.getByRole('list', { name: 'Stuck jobs' })
    expect(stuck).toHaveTextContent('1 running scan(s) stopped renewing')
    expect(stuck).toHaveTextContent('2 schedule(s) are over an hour late')
    expect(screen.getByText('Outside scheduler')).toBeVisible()
    expect(screen.getByText(/Gmail receipts: 3 failed/)).toBeVisible()
    const problem = screen.getByRole('row', {
      name: /Request failed unexpectedly/,
    })
    expect(problem).toHaveTextContent('route: /api/assets/{asset_id}')
    expect(problem).toHaveTextContent('5')
    expect(screen.getByText(/Alerts:\s*webhook/)).toBeVisible()
    expect(screen.getByText('3.5 MB')).toBeVisible()
    expect(screen.getByText('No limit')).toBeVisible()
    expect(
      screen.getByRole('list', { name: 'Largest accounts' }),
    ).toHaveTextContent('account-1a2b3c4d: 3.5 MB (3 photos, 1 documents)')

    await user.click(screen.getByRole('button', { name: 'Refresh' }))
    await vi.waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(
          ([url]) => String(url) === '/api/operator/overview',
        ),
      ).toHaveLength(2),
    )
  })

  it('reports a failed load', async () => {
    stub(true)
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) =>
        String(input) === '/api/operator/access'
          ? new Response(JSON.stringify({ operator: true }))
          : new Response('{}', { status: 500 }),
      ),
    )
    const user = userEvent.setup()
    render(<Workspace userId="operator" />)
    await user.click(await screen.findByRole('button', { name: 'Operations' }))
    expect(
      await screen.findByText('Unable to load the operations view.'),
    ).toHaveAttribute('role', 'alert')
  })
})
