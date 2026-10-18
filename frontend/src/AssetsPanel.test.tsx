import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { AssetsPanel } from './AssetsPanel'

afterEach(() => vi.unstubAllGlobals())

it('refreshes purchase associations when the current unit decision changes', async () => {
  const user = userEvent.setup()
  let corrected = false
  let purchaseReads = 0
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const asset = {
        id: 'asset',
        name: 'Synthetic unit',
        source_id: 'source',
        recorded_at: 100,
      }
      let value: unknown = { items: [], next_cursor: null }
      if (url.startsWith('/api/assets?'))
        value = { items: [asset], next_cursor: null }
      else if (url.startsWith('/api/assets/asset/purchases')) {
        purchaseReads++
        value = {
          items: corrected
            ? []
            : [
                {
                  key: 'line',
                  receipt_id: 'receipt',
                  index: 0,
                  source_id: 'source',
                  name: 'Original receipt',
                  quantity: 2,
                  unit: 1,
                  source_current: true,
                  claim: null,
                },
              ],
          next_cursor: null,
        }
      } else if (url === '/api/assets/asset')
        value = {
          asset,
          in_inventory: !corrected,
          action_head: '',
          facts: [],
          decisions: [
            {
              id: 'original',
              name: 'Synthetic unit',
              quantity: 2,
              unit: 0,
              manufacturer: null,
              model: null,
              serial: null,
              quote: 'Synthetic source',
              source_id: 'source',
              outcome: 'create',
              reason: 'Purchase',
              recorded_at: 100,
              superseded_at: corrected ? 200 : null,
            },
          ],
          next_fact_cursor: null,
          next_decision_cursor: null,
        }
      return new Response(JSON.stringify(value))
    }),
  )
  render(<AssetsPanel />)
  await user.click(
    await screen.findByRole('button', { name: 'Synthetic unit' }),
  )
  await screen.findByRole('heading', {
    name: 'Original receipt · receipt line 1',
  })
  corrected = true // another unit correction changed the shared decision, not this action head
  await user.click(screen.getByText('Make a correction'))
  await user.click(screen.getByRole('button', { name: 'Reload item' }))
  await screen.findByText(/No purchased receipt lines are currently linked/)
  expect(purchaseReads).toBe(2)
  expect(
    screen.queryByRole('heading', {
      name: 'Original receipt · receipt line 1',
    }),
  ).not.toBeInTheDocument()
})

it.each(['photo', 'document'])(
  'preserves deleted %s provenance when opening asset evidence',
  async (kind) => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        let result: unknown = { items: [], next_cursor: null }
        if (url.startsWith('/api/assets?'))
          result = {
            items: [
              {
                id: 'asset',
                name: 'Synthetic item',
                source_id: 'source',
                recorded_at: 100,
              },
            ],
            next_cursor: null,
          }
        else if (url === '/api/assets/asset')
          result = {
            asset: {
              id: 'asset',
              name: 'Synthetic item',
              source_id: 'source',
              recorded_at: 100,
            },
            in_inventory: true,
            decisions: [],
            facts: [],
            next_fact_cursor: null,
            next_decision_cursor: null,
          }
        else if (url.startsWith('/api/chat/sources/'))
          result = {
            id: 'source',
            text: 'Derived source text',
            next_offset: null,
            [kind]: {
              id: 'original',
              filename: 'synthetic.pdf',
              deleted_at: 123,
            },
          }
        return new Response(JSON.stringify(result))
      }),
    )
    render(<AssetsPanel csrfToken="csrf" />)
    await user.click(
      await screen.findByRole('button', { name: 'Synthetic item' }),
    )
    await user.click(
      await screen.findByRole('button', { name: 'View original evidence' }),
    )
    await screen.findByText(
      kind === 'photo'
        ? 'The original photo has been deleted. Derived text remains.'
        : 'The original PDF has been deleted; saved source history remains.',
    )
    expect(
      screen.queryByText('Original statement · not independently verified'),
    ).not.toBeInTheDocument()
    expect(screen.getByText('Derived source text')).toBeVisible()
    expect(
      screen.queryByRole('link', { name: 'Download original PDF' }),
    ).not.toBeInTheDocument()
  },
)

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
