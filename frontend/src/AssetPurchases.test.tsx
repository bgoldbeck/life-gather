import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { AssetPurchases } from './AssetPurchases'
afterEach(() => vi.unstubAllGlobals())
const item = {
  key: 'receipt:0',
  receipt_id: 'receipt',
  index: 0,
  source_id: 'source',
  name: 'Synthetic drill',
  quantity: 2,
  unit: 1,
  source_current: true,
  claim: {
    id: 'claim',
    revision: 1,
    line_total: '49.90',
    currency: 'USD',
    purchase_date: '2026-10-18',
    money_quote: 'Acme Drill Qty: 2; Line total: USD 49.90',
    date_quote: 'Purchase date: 2026-10-18',
    recorded_at: 1792348800000000,
  },
}
it('shows whole-line totals and opens the source and receipt history without AI', async () => {
  const user = userEvent.setup()
  const onOpen = vi.fn()
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      calls.push(url)
      return new Response(
        JSON.stringify(
          url === '/api/receipts/receipt'
            ? {
                id: 'receipt',
                state: 'no_items',
                items: [],
                source_id: 'source',
                current_source_id: 'source',
                stale: false,
                explanation: 'Synthetic history',
                result: {},
              }
            : { items: [item], next_cursor: null },
        ),
      )
    }),
  )
  render(<AssetPurchases assetId="asset" csrfToken="csrf" onOpen={onOpen} />)
  await screen.findByText('Line total: USD 49.90 · Purchase date: 2026-10-18')
  expect(screen.getByText(/This item is unit 1 of 2/)).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'View purchase source' }))
  expect(onOpen).toHaveBeenCalledWith('source')
  await user.click(
    screen.getByRole('button', { name: 'Open receipt and purchase history' }),
  )
  await screen.findByText('Synthetic history')
  expect(
    calls.every(
      (url) =>
        url.startsWith('/api/assets/') || url.startsWith('/api/receipts/'),
    ),
  ).toBe(true)
  await user.click(
    screen.getByRole('button', { name: 'Close purchase history' }),
  )
  expect(screen.queryByText('Synthetic history')).not.toBeInTheDocument()
})
it('refreshes a withdrawn claim as unknown and labels historical source evidence', async () => {
  const user = userEvent.setup()
  let cleared = false
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            items: [
              cleared
                ? {
                    ...item,
                    source_current: false,
                    claim: {
                      ...item.claim,
                      revision: 2,
                      line_total: null,
                      purchase_date: null,
                      money_quote: null,
                      date_quote: null,
                    },
                  }
                : item,
            ],
            next_cursor: null,
          }),
        ),
    ),
  )
  render(<AssetPurchases assetId="asset" csrfToken="csrf" onOpen={vi.fn()} />)
  await screen.findByText('Line total: USD 49.90 · Purchase date: 2026-10-18')
  cleared = true
  await user.click(
    screen.getByRole('button', { name: 'Refresh purchase records' }),
  )
  await screen.findByText('Line total: unknown · Purchase date: unknown')
  expect(screen.getByText(/withdrawn to unknown/)).toBeVisible()
  expect(screen.getByText(/Historical source:/)).toBeVisible()
  expect(
    screen.queryByText('Line total: USD 49.90 · Purchase date: 2026-10-18'),
  ).not.toBeInTheDocument()
})
it('loads bounded additional pages and provides a retry after a read failure', async () => {
  const user = userEvent.setup()
  let fail = true
  const paths: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      paths.push(url)
      if (fail) throw new TypeError('connection lost')
      return new Response(
        JSON.stringify({
          items: [{ ...item, key: url }],
          next_cursor: url.endsWith('cursor=') ? 'receipt:0' : null,
        }),
      )
    }),
  )
  render(<AssetPurchases assetId="asset" csrfToken="csrf" onOpen={vi.fn()} />)
  await screen.findByRole('alert')
  fail = false
  await user.click(
    screen.getByRole('button', { name: 'Refresh purchase records' }),
  )
  await screen.findByRole('button', { name: 'More purchase records' })
  await user.click(
    screen.getByRole('button', { name: 'More purchase records' }),
  )
  expect(paths.at(-1)).toContain('cursor=receipt%3A0')
  expect(
    screen.getAllByText('Line total: USD 49.90 · Purchase date: 2026-10-18'),
  ).toHaveLength(2)
})
