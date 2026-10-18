import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ReceiptProposalCard } from './ReceiptProposalCard'

afterEach(() => vi.unstubAllGlobals())
const items = ['Drill', 'Saw'].map((name, index) => ({
  name,
  manufacturer: 'Acme',
  model: null,
  serial: null,
  kind: 'mention',
  quote: `Acme ${name} Qty: ${index === 0 ? 2 : 1}`,
  quantity: index === 0 ? 2 : 1,
  quantity_quote: `Qty: ${index === 0 ? 2 : 1}`,
}))
const receipt = {
  id: 'receipt',
  source_id: 'source',
  current_source_id: 'source',
  stale: false,
  state: 'proposed',
  explanation: 'Synthetic receipt, ownership unknown.',
  items,
  result: {},
}

it('keeps edited receipt fields and fresh comparisons when automatic identity needs a manual choice', async () => {
  const user = userEvent.setup()
  const reviewed = vi.fn()
  let submitted: Record<string, unknown> | undefined
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/review')) {
        submitted = JSON.parse(String(init?.body))
        return new Response(
          JSON.stringify({
            ...receipt,
            automatic_outcome: 'review',
            automatic_checks: [
              {
                index: 0,
                outcome: 'review',
                reason: 'Names alone do not prove identity',
                check: 'fresh',
                reliable_ids: [],
                candidates: [{ id: 'existing', name: 'Existing drill' }],
              },
            ],
          }),
        )
      }
      return new Response(JSON.stringify(receipt))
    }),
  )
  render(
    <ReceiptProposalCard
      id="receipt"
      csrfToken="csrf"
      onOpen={vi.fn()}
      onReviewed={reviewed}
    />,
  )
  await screen.findByLabelText('Item name 1')
  await user.selectOptions(
    screen.getByLabelText('Your relationship to the selected items'),
    'purchase',
  )
  await user.selectOptions(screen.getByLabelText('Record item 1'), 'auto')
  await user.clear(screen.getByLabelText('Model 1'))
  await user.type(screen.getByLabelText('Model 1'), 'Reviewed model')
  await user.click(
    screen.getByRole('button', { name: 'Confirm selected receipt items' }),
  )
  await screen.findByText(/Nothing was recorded/)
  expect(screen.getByLabelText('Model 1')).toHaveValue('Reviewed model')
  expect(
    screen.getByLabelText('Your relationship to the selected items'),
  ).toHaveValue('purchase')
  expect(
    screen.getByRole('button', { name: 'Inspect Existing drill (existing)' }),
  ).toBeEnabled()
  expect(reviewed).not.toHaveBeenCalled()
  expect(submitted).toMatchObject({
    choices: [
      { action: 'auto', fields: { model: 'Reviewed model' } },
      { action: 'skip' },
    ],
  })
  await user.selectOptions(screen.getByLabelText('Record item 1'), 'new')
  expect(
    screen.getByRole('button', { name: 'Confirm selected receipt items' }),
  ).toBeEnabled()
})

it('requires explicit selected lines, ownership and duplicate checks before one atomic confirmation', async () => {
  const user = userEvent.setup()
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      let result: unknown = receipt
      if (url.endsWith('/preview'))
        result = { check: 'checked', candidates: [], reliable_ids: [] }
      if (url.endsWith('/review'))
        result = {
          ...receipt,
          state: 'accepted',
          result: { lines: [{ asset_ids: ['a', 'b'] }, { asset_ids: ['c'] }] },
        }
      return new Response(JSON.stringify(result))
    }),
  )
  render(<ReceiptProposalCard id="receipt" csrfToken="csrf" onOpen={vi.fn()} />)
  await screen.findByLabelText('Item name 1')
  expect(
    screen.getByRole('button', { name: 'Confirm selected receipt items' }),
  ).toBeDisabled()
  await user.selectOptions(
    screen.getByLabelText('Your relationship to the selected items'),
    'purchase',
  )
  await user.selectOptions(screen.getByLabelText('Record item 1'), 'new')
  await user.selectOptions(screen.getByLabelText('Record item 2'), 'new')
  await user.click(
    screen.getByRole('button', { name: 'Check item 1 and duplicates' }),
  )
  expect(
    screen.getByRole('button', { name: 'Confirm selected receipt items' }),
  ).toBeDisabled()
  await user.click(
    screen.getByRole('button', { name: 'Check item 2 and duplicates' }),
  )
  await user.click(
    screen.getByRole('button', { name: 'Confirm selected receipt items' }),
  )
  await screen.findByText(/Receipt confirmed. 3 physical units/)
  const review = calls.find((c) => c.url.endsWith('/review'))!
  expect(review.init?.headers).toMatchObject({ 'X-CSRF-Token': 'csrf' })
  const body = JSON.parse(String(review.init?.body))
  expect(
    body.choices.map(
      (c: { fields: { quantity: number } }) => c.fields.quantity,
    ),
  ).toEqual([2, 1])
  expect(
    body.choices.every(
      (c: { check: string; fields: { kind: string } }) =>
        c.check === 'checked' && c.fields.kind === 'purchase',
    ),
  ).toBe(true)
})

it.each(['new', 'auto'])(
  'freezes and retries the exact %s receipt review after a lost response',
  async (action) => {
    const user = userEvent.setup()
    const bodies: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        let result: unknown = receipt
        if (url.endsWith('/preview'))
          result = { check: 'checked', candidates: [], reliable_ids: [] }
        if (url.endsWith('/review')) {
          bodies.push(String(init?.body))
          if (bodies.length === 1) throw new TypeError('lost response')
          result = {
            ...receipt,
            state: 'accepted',
            result: { lines: [{ asset_ids: ['a', 'b'] }] },
          }
        }
        return new Response(JSON.stringify(result))
      }),
    )
    render(
      <ReceiptProposalCard id="receipt" csrfToken="csrf" onOpen={vi.fn()} />,
    )
    await screen.findByLabelText('Item name 1')
    await user.selectOptions(
      screen.getByLabelText('Your relationship to the selected items'),
      'possession',
    )
    await user.selectOptions(screen.getByLabelText('Record item 1'), action)
    if (action === 'new')
      await user.click(
        screen.getByRole('button', { name: 'Check item 1 and duplicates' }),
      )
    await user.click(
      screen.getByRole('button', { name: 'Confirm selected receipt items' }),
    )
    expect(
      await screen.findByRole('button', { name: 'Retry same receipt review' }),
    ).toBeEnabled()
    expect(screen.getByLabelText('Quantity 1')).toBeDisabled()
    expect(
      screen.getByRole('button', { name: 'Reject receipt proposal' }),
    ).toBeDisabled()
    await user.click(
      screen.getByRole('button', { name: 'Retry same receipt review' }),
    )
    await screen.findByText(/Receipt confirmed. 2 physical units/)
    expect(bodies).toHaveLength(2)
    expect(bodies[0]).toBe(bodies[1])
  },
)

it('requires distinct existing records for each physical unit', async () => {
  const user = userEvent.setup()
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async (url: string) =>
        new Response(
          JSON.stringify(
            url.endsWith('/preview')
              ? {
                  check: 'checked',
                  candidates: [
                    { id: 'a', name: 'Existing drill' },
                    { id: 'b', name: 'Other drill' },
                  ],
                  reliable_ids: [],
                }
              : receipt,
          ),
        ),
    ),
  )
  render(<ReceiptProposalCard id="receipt" csrfToken="csrf" onOpen={vi.fn()} />)
  await screen.findByLabelText('Item name 1')
  await user.selectOptions(
    screen.getByLabelText('Your relationship to the selected items'),
    'purchase',
  )
  await user.selectOptions(screen.getByLabelText('Record item 1'), 'link')
  await user.click(
    screen.getByRole('button', { name: 'Check item 1 and duplicates' }),
  )
  await user.selectOptions(
    screen.getByLabelText('Existing record for item 1, unit 1'),
    'a',
  )
  await user.selectOptions(
    screen.getByLabelText('Existing record for item 1, unit 2'),
    'a',
  )
  expect(
    screen.getByRole('button', { name: 'Confirm selected receipt items' }),
  ).toBeDisabled()
  await user.selectOptions(
    screen.getByLabelText('Existing record for item 1, unit 2'),
    'b',
  )
  expect(
    screen.getByRole('button', { name: 'Confirm selected receipt items' }),
  ).toBeEnabled()
})

it('allows rejection after the source was corrected', async () => {
  const user = userEvent.setup()
  const requests: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/review')) requests.push(JSON.parse(String(init?.body)))
      return new Response(
        JSON.stringify({
          ...receipt,
          stale: true,
          current_source_id: 'corrected',
          state: url.endsWith('/review') ? 'rejected' : 'proposed',
        }),
      )
    }),
  )
  const onOpen = vi.fn()
  render(<ReceiptProposalCard id="receipt" csrfToken="csrf" onOpen={onOpen} />)
  await screen.findByLabelText('Item name 1')
  expect(
    screen.queryByRole('button', { name: 'Confirm selected receipt items' }),
  ).not.toBeInTheDocument()
  await user.click(
    screen.getByRole('button', { name: 'Reject receipt proposal' }),
  )
  expect(requests).toEqual([
    expect.objectContaining({
      receipt_id: 'receipt',
      reject: true,
      choices: [],
    }),
  ])
})
