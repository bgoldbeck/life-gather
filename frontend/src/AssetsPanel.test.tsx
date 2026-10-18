import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { AssetsPanel } from './AssetsPanel'

afterEach(() => vi.unstubAllGlobals())
it('browses private assets, details, original evidence and history pages safely', async () => {
  const user = userEvent.setup()
  const fetcher = vi.fn(async (url: string) => {
    let value: unknown
    if (url.startsWith('/api/photos') || url.startsWith('/api/credentials'))
      value = { items: [], next_cursor: null }
    else if (url === '/api/settings') value = { allow_external_ai: false }
    else if (url.startsWith('/api/assets?'))
      value = {
        items: [
          {
            id: 'asset',
            name: 'Synthetic drill',
            source_id: 'source',
            recorded_at: 100,
            in_inventory: true,
          },
        ],
        next_cursor: url.includes('cursor=') ? null : 'next',
      }
    else if (url.startsWith('/api/chat/sources'))
      value = {
        id: 'source',
        text: '<script>original evidence</script>',
        next_offset: null,
      }
    else
      value = {
        asset: {
          id: 'asset',
          name: 'Synthetic drill',
          source_id: 'source',
          recorded_at: 100,
        },
        in_inventory: true,
        decisions: [
          {
            id: url.includes('decision_cursor') ? 'd2' : 'd1',
            name: 'Synthetic drill',
            manufacturer: null,
            model: null,
            serial: null,
            quote: 'I own a synthetic drill.',
            source_id: 'source',
            outcome: 'create',
            reason: 'Stated possession',
            recorded_at: 100,
            superseded_at: null,
          },
        ],
        facts: [],
        next_fact_cursor: null,
        next_decision_cursor: url.includes('decision_cursor') ? null : 'd1',
      }
    return new Response(JSON.stringify(value))
  })
  vi.stubGlobal('fetch', fetcher)
  render(<AssetsPanel />)
  await user.click(
    await screen.findByRole('button', { name: 'Synthetic drill' }),
  )
  expect(
    await screen.findByRole('heading', { name: 'Synthetic drill' }),
  ).toBeVisible()
  expect(screen.getAllByText('Unknown')).toHaveLength(3)
  await user.click(screen.getByRole('button', { name: 'More decisions' }))
  expect(await screen.findAllByText('Stated possession')).toHaveLength(2)
  await user.click(
    screen.getByRole('button', { name: 'View original evidence' }),
  )
  expect(
    await screen.findByText('<script>original evidence</script>'),
  ).toBeVisible()
  expect(document.querySelector('script')).toBeNull()
  await user.type(screen.getByLabelText('Search item names'), 'drill')
  await user.click(screen.getByRole('button', { name: 'Search assets' }))
  expect(fetcher.mock.calls.some(([url]) => url.includes('query=drill'))).toBe(
    true,
  )
  await user.click(screen.getByLabelText('Include historical records'))
  expect(
    fetcher.mock.calls.some(([url]) => url.includes('include_history=true')),
  ).toBe(true)
})

it('shows an honest empty state and handles unavailable data', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ items: [], next_cursor: null })),
      ),
  )
  render(<AssetsPanel />)
  expect(await screen.findByText(/No assets found/)).toBeVisible()
})
