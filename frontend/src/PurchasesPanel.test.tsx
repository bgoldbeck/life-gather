import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { PurchasesPanel } from './PurchasesPanel'

afterEach(() => vi.unstubAllGlobals())

it('reviews a saved source and retries the identical uncertain evidence request', async () => {
  const user = userEvent.setup()
  const writes: RequestInit[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        writes.push(init)
        if (writes.length === 1) throw new Error('Lost response')
        return new Response('{"purchase_id":"purchase","id":"evidence"}')
      }
      const page = url.includes('/memories')
        ? {
            items: [
              { id: 'source', text: 'Synthetic Store order P1', kind: 'notes' },
            ],
            next_cursor: null,
          }
        : url.includes('/history')
          ? { items: [], next_revision: null }
          : url.includes('/sources/source')
            ? {
                source_id: 'source',
                root_source_id: 'source',
                current_source_id: 'source',
                text: 'Synthetic Store order P1',
                can_attach: true,
                head: null,
              }
            : { items: [], next_cursor: null }
      return new Response(JSON.stringify(page))
    }),
  )
  render(<PurchasesPanel csrfToken="csrf" />)
  await user.click(
    await screen.findByRole('button', {
      name: /^Use source: Synthetic Store order P1$/,
    }),
  )
  expect(writes).toHaveLength(0)
  await user.type(await screen.findByLabelText('Retailer'), 'Synthetic Store')
  await user.type(screen.getByLabelText('Private account label'), 'mine')
  await user.type(screen.getByLabelText('Order ID'), 'P1')
  await user.type(
    screen.getByLabelText('Exact evidence quote'),
    'Synthetic Store order P1',
  )
  await user.type(
    screen.getByLabelText('Association or correction reason'),
    'Synthetic explicit review',
  )
  await user.click(
    screen.getByRole('button', { name: /^Save purchase evidence$/ }),
  )
  await screen.findByRole('alert')
  await user.click(
    screen.getByRole('button', { name: /^Retry evidence request$/ }),
  )
  await waitFor(() => expect(writes).toHaveLength(2))
  expect(writes[0].body).toEqual(writes[1].body)
  expect(writes[0].headers).toMatchObject({ 'X-CSRF-Token': 'csrf' })
  expect(JSON.parse(String(writes[0].body))).toMatchObject({
    source_id: 'source',
    expected_head: null,
    role: 'order',
    order_id: 'P1',
  })
})

it('withdraws an explicitly selected stale association with its current head', async () => {
  const user = userEvent.setup()
  const writes: { url: string; init?: RequestInit }[] = []
  const head = {
    id: 'head',
    purchase_id: 'purchase',
    source_id: 'source',
    root_source_id: 'source',
    revision: 1,
    previous_id: null,
    superseded_at: null,
    state: 'active',
    role: 'receipt',
    quote: 'Historical evidence',
    amount_minor: null,
    currency: null,
    money_quote: null,
    occurred_on: null,
    date_quote: null,
    reason: 'Earlier review',
    recorded_at: 1000000,
    source_current: false,
  }
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        writes.push({ url, init })
        return new Response(
          JSON.stringify({ ...head, id: 'withdrawn', state: 'withdrawn' }),
        )
      }
      return new Response(
        JSON.stringify(
          url.includes('/memories')
            ? {
                items: [{ id: 'source', text: 'Historical evidence' }],
                next_cursor: null,
              }
            : url.includes('/history')
              ? { items: [head], next_revision: null }
              : url.includes('/sources/source')
                ? {
                    source_id: 'source',
                    root_source_id: 'source',
                    current_source_id: 'new-source',
                    text: 'Historical evidence',
                    can_attach: false,
                    head,
                  }
                : { items: [], next_cursor: null },
        ),
      )
    }),
  )
  render(<PurchasesPanel csrfToken="csrf" />)
  await user.click(
    await screen.findByRole('button', {
      name: /^Use source: Historical evidence$/,
    }),
  )
  await screen.findByRole('button', { name: /^Withdraw selected association$/ })
  expect(
    screen.getByRole('button', { name: /^Save purchase evidence$/ }),
  ).toBeDisabled()
  await user.type(
    screen.getByLabelText('Association or correction reason'),
    'Withdraw outdated association',
  )
  await user.click(
    screen.getByRole('button', { name: /^Withdraw selected association$/ }),
  )
  await waitFor(() => expect(writes).toHaveLength(1))
  expect(writes[0].url).toBe('/api/purchases/withdraw')
  expect(JSON.parse(String(writes[0].init?.body))).toMatchObject({
    source_id: 'source',
    expected_head: 'head',
    reason: 'Withdraw outdated association',
  })
})

it('ignores late source reads after a different source is selected', async () => {
  const user = userEvent.setup()
  let finish: ((response: Response) => void) | undefined
  const writes: RequestInit[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') writes.push(init)
      if (url.endsWith('/sources/old'))
        return new Promise<Response>((resolve) => {
          finish = resolve
        })
      const value = url.includes('/memories')
        ? {
            items: [
              { id: 'old', text: 'Old source' },
              { id: 'new', text: 'New source' },
            ],
            next_cursor: null,
          }
        : url.endsWith('/sources/new')
          ? {
              source_id: 'new',
              root_source_id: 'new',
              current_source_id: 'new',
              text: 'Current selected evidence',
              can_attach: true,
              head: null,
            }
          : url.includes('/history')
            ? { items: [], next_revision: null }
            : { items: [], next_cursor: null }
      return new Response(JSON.stringify(value))
    }),
  )
  render(<PurchasesPanel csrfToken="csrf" />)
  await user.click(
    await screen.findByRole('button', { name: /^Use source: Old source$/ }),
  )
  await user.click(
    screen.getByRole('button', { name: /^Use source: New source$/ }),
  )
  await screen.findByText('Current selected evidence')
  finish?.(
    new Response(
      JSON.stringify({
        source_id: 'old',
        text: 'Late old evidence',
        can_attach: true,
        head: null,
      }),
    ),
  )
  await waitFor(() =>
    expect(screen.queryByText('Late old evidence')).not.toBeInTheDocument(),
  )
  expect(writes).toHaveLength(0)
})
