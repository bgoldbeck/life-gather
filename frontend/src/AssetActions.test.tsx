import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { AssetActions } from './AssetActions'

afterEach(() => vi.unstubAllGlobals())
it('reports failed reloads, preserves the draft and allows a successful retry without writing', async () => {
  const user = userEvent.setup()
  const changed = vi
    .fn()
    .mockRejectedValueOnce(new Error('Synthetic connection failure'))
    .mockResolvedValue(undefined)
  const fetcher = vi.fn()
  vi.stubGlobal('fetch', fetcher)
  render(
    <AssetActions
      assetId="item"
      head="head"
      decisions={[]}
      csrfToken="csrf"
      onChanged={changed}
    />,
  )
  await user.selectOptions(screen.getByLabelText('Ownership statement'), 'sold')
  await user.type(
    screen.getByLabelText('Why are you changing it?'),
    'Keep this synthetic draft.',
  )
  await user.click(screen.getByRole('button', { name: 'Reload item' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Your draft is unchanged',
  )
  expect(screen.getByLabelText('Why are you changing it?')).toHaveValue(
    'Keep this synthetic draft.',
  )
  expect(screen.getByLabelText('Ownership statement')).toHaveValue('sold')
  await user.click(screen.getByRole('button', { name: 'Reload item' }))
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(changed).toHaveBeenCalledTimes(2)
  expect(fetcher).not.toHaveBeenCalled()
})

it('opens the exact decision source, compares targets without choosing, and clears hidden search selections', async () => {
  const user = userEvent.setup()
  const open = vi.fn().mockResolvedValue(undefined)
  const writes: Record<string, unknown>[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.startsWith('/api/assets?'))
        return new Response(
          JSON.stringify({
            items: [
              {
                id: url.includes('second') ? 'second' : 'first',
                name: 'Same name',
                recorded_at: 100,
              },
            ],
            next_cursor: null,
          }),
        )
      if (url.includes('?limit=3'))
        return new Response(
          JSON.stringify({
            asset: {
              id: 'first',
              name: 'Same name',
              source_id: 'target-source',
            },
            in_inventory: true,
            decisions: [],
          }),
        )
      writes.push(JSON.parse(String(init?.body)))
      return new Response(JSON.stringify({ id: 'saved' }))
    }),
  )
  render(
    <AssetActions
      assetId="item"
      assetName="Source item"
      head=""
      decisions={[
        {
          id: 'decision',
          name: 'Receipt item',
          quote: 'Exact synthetic receipt passage.',
          source_id: 'receipt-source',
          recorded_at: 100,
          superseded_at: null,
        },
      ]}
      csrfToken="csrf"
      onChanged={vi.fn()}
      onOpen={open}
    />,
  )
  await user.selectOptions(
    screen.getByLabelText('Change to make'),
    'reassociate',
  )
  await user.selectOptions(
    screen.getByLabelText('Current decision'),
    'decision',
  )
  expect(screen.getByText('Exact synthetic receipt passage.')).toBeVisible()
  await user.click(
    screen.getByRole('button', { name: 'Open selected decision source' }),
  )
  expect(open).toHaveBeenCalledWith('receipt-source')
  await user.click(screen.getByRole('button', { name: 'Find target items' }))
  await user.click(
    screen.getByRole('button', { name: 'Inspect Same name (first)' }),
  )
  await screen.findByRole('button', { name: 'Open candidate original source' })
  expect(screen.getByLabelText('Evidence belongs to')).toHaveValue('')
  expect(writes).toHaveLength(0)
  await user.selectOptions(
    screen.getByLabelText('Evidence belongs to'),
    'first',
  )
  await user.type(
    screen.getByLabelText('Why are you changing it?'),
    'Synthetic correction.',
  )
  expect(screen.getByRole('button', { name: 'Save correction' })).toBeEnabled()
  await user.type(screen.getByLabelText('Find an existing item'), 'second')
  expect(screen.getByLabelText('Evidence belongs to')).toHaveValue('')
  expect(screen.getByRole('button', { name: 'Save correction' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Find target items' }))
  await user.selectOptions(
    screen.getByLabelText('Evidence belongs to'),
    'second',
  )
  await user.click(screen.getByRole('button', { name: 'Save correction' }))
  expect(writes).toHaveLength(1)
  expect(writes[0]).toMatchObject({
    target_asset_id: 'second',
    decision_id: 'decision',
  })
})

it('moves only the selected receipt unit to an explicit existing item and excludes multi-unit undo', async () => {
  const user = userEvent.setup()
  const fetcher = vi.fn(
    async (url: string) =>
      new Response(
        JSON.stringify(
          url.startsWith('/api/assets?')
            ? {
                items: [
                  { id: 'target', name: 'Replacement', recorded_at: 100 },
                ],
                next_cursor: null,
              }
            : { id: 'saved' },
        ),
      ),
  )
  vi.stubGlobal('fetch', fetcher)
  render(
    <AssetActions
      assetId="item"
      head=""
      decisions={[
        {
          id: 'pair',
          recorded_at: 100,
          superseded_at: null,
          quantity: 2,
          unit: 1,
        },
      ]}
      csrfToken="csrf"
      onChanged={vi.fn()}
    />,
  )
  await user.selectOptions(screen.getByLabelText('Change to make'), 'undo')
  expect(
    screen.queryByRole('option', { name: /this item is unit/ }),
  ).not.toBeInTheDocument()
  await user.selectOptions(
    screen.getByLabelText('Change to make'),
    'reassociate',
  )
  await user.selectOptions(screen.getByLabelText('Current decision'), 'pair')
  expect(
    screen.getByRole('option', { name: /this item is unit 2 of 2/ }),
  ).toBeInTheDocument()
  expect(
    screen.getByRole('option', { name: /A different physical item/ }),
  ).toBeDisabled()
  await user.type(
    screen.getByLabelText('Why are you changing it?'),
    'This unit belongs to my replacement.',
  )
  expect(screen.getByRole('button', { name: 'Save correction' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Find target items' }))
  await user.selectOptions(
    screen.getByLabelText('Evidence belongs to'),
    'target',
  )
  await user.click(screen.getByRole('button', { name: 'Save correction' }))
  const write = fetcher.mock.calls.find(
    (call) => call[0] === '/api/assets/actions',
  )!
  expect(
    JSON.parse((write as unknown as [string, RequestInit])[1].body as string),
  ).toMatchObject({
    operation: 'reassociate',
    asset_id: 'item',
    decision_id: 'pair',
    target_asset_id: 'target',
  })
})

it('records an explicit sourced sale with the expected version and CSRF', async () => {
  const user = userEvent.setup()
  const changed = vi.fn().mockResolvedValue(undefined)
  const fetcher = vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify({ id: 'action' })))
  vi.stubGlobal('fetch', fetcher)
  render(
    <AssetActions
      assetId="item"
      head="previous"
      decisions={[]}
      csrfToken="csrf"
      onChanged={changed}
    />,
  )
  expect(screen.getByRole('button', { name: 'Save correction' })).toBeDisabled()
  await user.selectOptions(screen.getByLabelText('Ownership statement'), 'sold')
  await user.type(screen.getByLabelText('Event date, if known'), '2024-05-04')
  await user.type(
    screen.getByLabelText('Why are you changing it?'),
    'I sold this item.',
  )
  await user.click(screen.getByRole('button', { name: 'Save correction' }))
  expect(changed).toHaveBeenCalledOnce()
  const init = fetcher.mock.calls[0][1]
  expect(init.headers).toMatchObject({ 'X-CSRF-Token': 'csrf' })
  expect(JSON.parse(init.body)).toMatchObject({
    asset_id: 'item',
    expected_action_id: 'previous',
    operation: 'ownership',
    status: 'sold',
    event_date: '2024-05-04',
    note: 'I sold this item.',
  })
})

it('requires an explicit reassociation target and safely retries a lost response', async () => {
  const user = userEvent.setup()
  const bodies: string[] = []
  let lost = true
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.startsWith('/api/assets?'))
      return new Response(
        JSON.stringify({
          items: [{ id: 'other', name: 'Other tool', recorded_at: 100 }],
          next_cursor: null,
        }),
      )
    bodies.push(init!.body as string)
    if (lost) {
      lost = false
      throw new TypeError('Lost response')
    }
    return new Response(JSON.stringify({ id: 'saved' }))
  })
  vi.stubGlobal('fetch', fetcher)
  render(
    <AssetActions
      assetId="item"
      head=""
      decisions={[{ id: 'decision', recorded_at: 100, superseded_at: null }]}
      csrfToken="csrf"
      onChanged={vi.fn().mockResolvedValue(undefined)}
    />,
  )
  await user.selectOptions(
    screen.getByLabelText('Change to make'),
    'reassociate',
  )
  await user.selectOptions(
    screen.getByLabelText('Current decision'),
    'decision',
  )
  await user.type(
    screen.getByLabelText('Why are you changing it?'),
    'Wrong physical item.',
  )
  expect(screen.getByRole('button', { name: 'Save correction' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Find target items' }))
  await user.selectOptions(
    screen.getByLabelText('Evidence belongs to'),
    'other',
  )
  await user.click(screen.getByRole('button', { name: 'Save correction' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Retry safely')
  expect(screen.getByLabelText('Why are you changing it?')).toBeDisabled()
  await user.click(
    screen.getByRole('button', { name: 'Retry same correction' }),
  )
  expect(bodies).toHaveLength(2)
  expect(bodies[0]).toBe(bodies[1])
  expect(JSON.parse(bodies[0])).toMatchObject({
    operation: 'reassociate',
    decision_id: 'decision',
    target_asset_id: 'other',
  })
})
