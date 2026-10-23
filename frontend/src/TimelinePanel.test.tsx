import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TimelinePanel, type Dashboard } from './TimelinePanel'

afterEach(() => vi.unstubAllGlobals())

const months = [
  '2026-05',
  '2026-06',
  '2026-07',
  '2026-08',
  '2026-09',
  '2026-10',
]
const zeros = [0, 0, 0, 0, 0, 0]

const dashboard: Dashboard = {
  months,
  today: '2026-10-23',
  spending: [
    {
      currency: 'USD',
      total_minor: 4990,
      line_count: 1,
      by_month: [0, 0, 0, 0, 0, 4990],
      undated_minor: 0,
      undated_count: 0,
      largest: [
        {
          receipt_id: 'receipt-1',
          index: 0,
          source_id: 'source-1',
          name: 'Synthetic drill',
          total_minor: 4990,
          purchase_date: '2026-10-18',
        },
      ],
    },
    {
      currency: 'EUR',
      total_minor: 0,
      line_count: 0,
      by_month: zeros,
      undated_minor: 1200,
      undated_count: 1,
      largest: [],
    },
  ],
  missing_total_count: 1,
  activity: {
    purchase: [0, 0, 0, 0, 0, 2],
    asset: [0, 0, 1, 0, 0, 3],
    document: zeros,
    photo: zeros,
    maintenance_done: [0, 0, 0, 0, 0, 1],
  },
  overdue_count: 1,
  upcoming: [
    {
      task_id: 'task-1',
      title: 'Wash',
      due_on: '2026-10-01',
      overdue: true,
      entity_id: 'vehicle-1',
      entity_name: 'Synthetic vehicle',
      entity_kind: 'place',
    },
  ],
  truncated: false,
}

const october = {
  month: '2026-10',
  truncated: false,
  items: [
    {
      id: 'purchase:receipt-1:0',
      kind: 'purchase',
      date: '2026-10-18',
      date_basis: 'stated',
      title: 'Synthetic drill',
      detail: 'Qty 2',
      amount_minor: 4990,
      currency: 'USD',
      target: { view: 'Memories', id: 'source-1' },
    },
    {
      id: 'asset:asset-1',
      kind: 'asset',
      date: '2026-10-18',
      date_basis: 'recorded',
      title: 'Synthetic drill',
      detail: 'Added to your assets',
      amount_minor: null,
      currency: null,
      target: { view: 'Assets', id: 'asset-1' },
    },
  ],
}

function stub() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.startsWith('/api/insights/dashboard'))
      return new Response(JSON.stringify(dashboard))
    if (url.startsWith('/api/insights/timeline?month=2026-10'))
      return new Response(JSON.stringify(october))
    if (url.startsWith('/api/insights/timeline'))
      return new Response(
        JSON.stringify({ month: '2026-09', items: [], truncated: false }),
      )
    return new Response('{}', { status: 404 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('Timeline', () => {
  it('shows spending, activity and the current month, and opens records', async () => {
    const fetchMock = stub()
    const onOpen = vi.fn()
    render(<TimelinePanel onOpen={onOpen} />)
    expect(
      await screen.findAllByText('$49.90', { selector: 'strong' }),
    ).toHaveLength(2)
    expect(String(fetchMock.mock.calls[0][0])).toContain('months=12')
    expect(screen.getByText(/1 item bought in this range has no total/))
    const money = screen.getByRole('group', {
      name: 'Spending by month in USD',
    })
    expect(
      within(money).getByRole('button', { name: /October 2026: \$49\.90/ }),
    ).toHaveAttribute('aria-pressed', 'true')

    // Currencies are never mixed: EUR has its own view with its undated total.
    await userEvent.click(screen.getByRole('button', { name: 'EUR' }))
    expect(screen.getByText(/1 total \(€12\.00\) has no purchase date/))

    const events = await screen.findAllByRole('button', {
      name: /Synthetic drill/,
    })
    expect(screen.getByText(/saved in LifeGather/))
    await userEvent.click(
      events.find((item) => item.textContent?.includes('$49.90'))!,
    )
    expect(onOpen).toHaveBeenCalledWith({ view: 'Memories', id: 'source-1' })

    await userEvent.click(screen.getByRole('button', { name: 'Wash' }))
    expect(onOpen).toHaveBeenLastCalledWith({
      view: 'Profiles',
      id: 'vehicle-1',
    })
    expect(screen.getByText('1 overdue'))
  })

  it('filters event kinds and moves between months', async () => {
    const fetchMock = stub()
    render(<TimelinePanel onOpen={vi.fn()} />)
    await screen.findByRole('heading', { name: 'October 2026' })
    await screen.findByText(/saved in LifeGather/)
    await userEvent.click(screen.getByRole('button', { name: 'Assets added' }))
    expect(screen.queryByText(/saved in LifeGather/)).toBeNull()
    expect(screen.getByRole('button', { name: 'Next month' })).toBeDisabled()
    await userEvent.click(
      screen.getByRole('button', { name: 'Previous month' }),
    )
    expect(
      await screen.findByText('Nothing recorded in September 2026.'),
    ).toBeInTheDocument()
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes('2026-09')),
    ).toBe(true)
    await userEvent.click(screen.getByRole('button', { name: '24 months' }))
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes('months=24')),
    ).toBe(true)
  })

  it('reports a failed load', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('{}', { status: 500 })),
    )
    render(<TimelinePanel onOpen={vi.fn()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Unable to load your timeline.',
    )
  })
})

describe('Timeline busy months', () => {
  it('shows the first events and opens the rest on request', async () => {
    const many = Array.from({ length: 15 }, (_, index) => ({
      ...october.items[1],
      id: `asset:asset-${index}`,
      title: `Synthetic item ${String(index).padStart(2, '0')}`,
    }))
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) =>
        String(input).startsWith('/api/insights/dashboard')
          ? new Response(JSON.stringify(dashboard))
          : new Response(JSON.stringify({ ...october, items: many })),
      ),
    )
    render(<TimelinePanel onOpen={vi.fn()} />)
    expect(await screen.findAllByText(/^Synthetic item/)).toHaveLength(12)
    await userEvent.click(
      screen.getByRole('button', { name: 'Show all 15 events' }),
    )
    expect(screen.getAllByText(/^Synthetic item/)).toHaveLength(15)
  })
})
