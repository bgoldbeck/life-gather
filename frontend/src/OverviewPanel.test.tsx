import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { OverviewPanel, type Overview } from './OverviewPanel'

afterEach(() => vi.unstubAllGlobals())

const today = '2026-10-23'
const noon = new Date(`${today}T12:00:00`).getTime() * 1000

const overview: Overview = {
  today,
  counts: { assets: 3, documents: 2, photos: 5, memories: 7 },
  review_count: 2,
  overdue_count: 1,
  upcoming: [
    {
      task_id: 'task-1',
      title: 'Replace filter',
      due_on: '2026-10-01',
      overdue: true,
      entity_id: 'vehicle-1',
      entity_name: 'Synthetic vehicle',
      entity_kind: 'asset',
    },
  ],
  recent: [
    {
      kind: 'photo',
      title: 'synthetic.jpg',
      recorded_at: noon,
      target: { view: 'Photos', id: 'photo-1' },
    },
    {
      kind: 'asset',
      title: 'Synthetic drill',
      recorded_at: noon - 86_400_000_000,
      target: { view: 'Assets', id: 'asset-1' },
    },
  ],
}

function stub(body: unknown, status = 200) {
  const fetch = vi.fn(
    async () => new Response(JSON.stringify(body), { status }),
  )
  vi.stubGlobal('fetch', fetch)
  return fetch
}

function setup() {
  const props = {
    onNavigate: vi.fn(),
    onOpen: vi.fn(),
    onOpenAssistant: vi.fn(),
  }
  render(<OverviewPanel {...props} />)
  return props
}

describe('Overview', () => {
  it('makes the hero icons labelled links to their sections', async () => {
    stub(overview)
    const user = userEvent.setup()
    const props = setup()
    const hero = screen.getByRole('navigation', {
      name: 'Explore your workspace',
    })
    const memories = within(hero).getByRole('button', {
      name: 'Open Memories',
    })
    expect(memories).toHaveTextContent('Memories')
    await user.click(memories)
    expect(props.onNavigate).toHaveBeenCalledWith('Memories')
    await user.click(within(hero).getByRole('button', { name: 'Open Assets' }))
    expect(props.onNavigate).toHaveBeenCalledWith('Assets')
    await user.click(within(hero).getByRole('button', { name: 'Open Graph' }))
    expect(props.onNavigate).toHaveBeenCalledWith('Graph')
    // Keyboard: the chat icon is reachable with Tab and opens with Enter.
    within(hero).getByRole('button', { name: 'Open Assets' }).focus()
    await user.tab()
    expect(
      within(hero).getByRole('button', { name: 'Open Chat' }),
    ).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(props.onOpenAssistant).toHaveBeenCalledOnce()
  })

  it('shows counts, waiting work and recent records that open', async () => {
    const fetch = stub(overview)
    const user = userEvent.setup()
    const props = setup()
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/insights/overview'),
      expect.anything(),
    )
    const tiles = await screen.findByRole('region', { name: 'At a glance' })
    const photos = within(tiles).getByRole('button', { name: /Photos/ })
    expect(await within(photos).findByText('5')).toBeVisible()
    await user.click(photos)
    expect(props.onNavigate).toHaveBeenCalledWith('Photos')

    const attention = screen.getByRole('region', {
      name: 'Needs your attention',
    })
    expect(within(attention).getByText('3 waiting')).toBeVisible()
    await user.click(
      within(attention).getByRole('button', { name: '2 items to review' }),
    )
    expect(props.onNavigate).toHaveBeenCalledWith('Review')
    expect(within(attention).getByText(/Overdue/)).toBeVisible()
    await user.click(
      within(attention).getByRole('button', { name: 'Replace filter' }),
    )
    expect(props.onOpen).toHaveBeenCalledWith({
      view: 'Assets',
      id: 'vehicle-1',
    })

    const recent = screen.getByRole('region', { name: 'Recently added' })
    expect(within(recent).getByText('Today')).toBeVisible()
    expect(within(recent).getByText('Yesterday')).toBeVisible()
    await user.click(
      within(recent).getByRole('button', { name: /Photo:\s*synthetic\.jpg/ }),
    )
    expect(props.onOpen).toHaveBeenCalledWith({ view: 'Photos', id: 'photo-1' })
    expect(screen.queryByText('Your story starts here')).not.toBeInTheDocument()
    await user.click(
      screen.getByRole('button', { name: 'Charts on the Timeline' }),
    )
    expect(props.onNavigate).toHaveBeenCalledWith('Timeline')
  })

  it('offers first steps and a calm empty state to a new account', async () => {
    stub({
      ...overview,
      counts: { assets: 0, documents: 0, photos: 0, memories: 0 },
      review_count: 0,
      overdue_count: 0,
      upcoming: [],
      recent: [],
    })
    setup()
    expect(await screen.findByText(/You're all caught up/)).toBeVisible()
    expect(screen.getByText(/Nothing saved yet/)).toBeVisible()
    expect(screen.getByText('Your story starts here')).toBeVisible()
  })

  it('says when the overview cannot load and retries', async () => {
    const fetch = stub({ detail: 'nope' }, 500)
    const user = userEvent.setup()
    setup()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Unable to load your overview.',
    )
    stub(overview)
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('3 waiting')).toBeVisible()
    expect(fetch).toHaveBeenCalledOnce()
  })
})
