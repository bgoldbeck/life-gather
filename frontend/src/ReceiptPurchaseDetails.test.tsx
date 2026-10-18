import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ReceiptPurchaseDetails } from './ReceiptPurchaseDetails'
afterEach(() => vi.unstubAllGlobals())
const empty = {
  current_head: null,
  current: null,
  can_edit: true,
  items: [],
  next_revision: null,
  quantity: 2,
}
const revision = {
  id: 'revision',
  revision: 1,
  line_total: '49.90',
  total_minor: 4990,
  currency: 'USD',
  purchase_date: '2026-10-18',
  money_quote: 'Acme Drill Qty: 2; Line total: USD 49.90',
  date_quote: 'Purchase date: 2026-10-18',
  reason: 'Copied source',
  recorded_at: 1792348800000000,
}
it('records the source line total as an exact string for all units only after submission', async () => {
  const user = userEvent.setup()
  const saves: Record<string, unknown>[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/save')) {
        saves.push(JSON.parse(String(init?.body)))
        return new Response(JSON.stringify(revision))
      }
      return new Response(JSON.stringify(empty))
    }),
  )
  render(<ReceiptPurchaseDetails id="receipt" index={0} csrfToken="csrf" />)
  await screen.findByLabelText('USD line total 1')
  expect(saves).toHaveLength(0)
  expect(
    screen.getByRole('button', { name: 'Save purchase details' }),
  ).toBeDisabled()
  await user.type(screen.getByLabelText('USD line total 1'), '49.90')
  await user.type(
    screen.getByLabelText('Line-total passage 1'),
    revision.money_quote,
  )
  await user.type(
    screen.getByLabelText('Purchase date 1'),
    revision.purchase_date,
  )
  await user.type(
    screen.getByLabelText('Purchase-date passage 1'),
    revision.date_quote,
  )
  await user.type(screen.getByLabelText('Revision reason 1'), 'Copied source')
  await user.click(
    screen.getByRole('button', { name: 'Save purchase details' }),
  )
  await screen.findByText(/Purchase details saved with source evidence/)
  expect(screen.getByText(/Revision 1 ·/)).toHaveTextContent(
    new Date(revision.recorded_at / 1000).toLocaleString(),
  )
  expect(saves).toEqual([
    expect.objectContaining({
      line_total: '49.90',
      purchase_date: '2026-10-18',
      expected_head: null,
    }),
  ])
  expect(
    screen.getByText('Line total: USD 49.90 · Purchase date: 2026-10-18'),
  ).toBeVisible()
})
it('freezes the fields and replays the same request after a lost response', async () => {
  const user = userEvent.setup()
  const saves: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/save')) {
        saves.push(String(init?.body))
        if (saves.length === 1) throw new TypeError('Lost response')
        return new Response(JSON.stringify(revision))
      }
      return new Response(JSON.stringify(empty))
    }),
  )
  render(<ReceiptPurchaseDetails id="receipt" index={0} csrfToken="csrf" />)
  await screen.findByLabelText('Revision reason 1')
  await user.type(screen.getByLabelText('Revision reason 1'), 'Copied source')
  await user.click(
    screen.getByRole('button', { name: 'Save purchase details' }),
  )
  await screen.findByRole('button', { name: 'Retry same purchase details' })
  expect(screen.getByLabelText('USD line total 1')).toBeDisabled()
  expect(
    screen.getByRole('button', { name: 'Reload purchase details' }),
  ).toBeDisabled()
  await user.click(
    screen.getByRole('button', { name: 'Retry same purchase details' }),
  )
  await screen.findByText(/Purchase details saved with source evidence/)
  expect(saves).toHaveLength(2)
  expect(saves[1]).toBe(saves[0])
})
it('keeps earlier revisions visible when details are withdrawn to unknown', async () => {
  const user = userEvent.setup()
  const requests: Record<string, unknown>[] = []
  const cleared = {
    ...revision,
    id: 'clear',
    revision: 2,
    line_total: null,
    total_minor: null,
    currency: null,
    purchase_date: null,
    money_quote: null,
    date_quote: null,
    reason: 'Withdraw unsupported claims',
  }
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/save')) {
        requests.push(JSON.parse(String(init?.body)))
        return new Response(JSON.stringify(cleared))
      }
      return new Response(
        JSON.stringify({
          ...empty,
          current_head: 'revision',
          current: revision,
          items: [revision],
        }),
      )
    }),
  )
  render(<ReceiptPurchaseDetails id="receipt" index={0} csrfToken="csrf" />)
  await screen.findByDisplayValue('49.90')
  for (const label of [
    'USD line total 1',
    'Line-total passage 1',
    'Purchase date 1',
    'Purchase-date passage 1',
  ])
    await user.clear(screen.getByLabelText(label))
  await user.type(
    screen.getByLabelText('Revision reason 1'),
    'Withdraw unsupported claims',
  )
  await user.click(
    screen.getByRole('button', { name: 'Save purchase details' }),
  )
  await screen.findByText('Line total: unknown · Purchase date: unknown')
  expect(
    screen.getByText('Line total: USD 49.90 · Purchase date: 2026-10-18'),
  ).toBeVisible()
  expect(requests[0]).toMatchObject({
    expected_head: 'revision',
    line_total: null,
    purchase_date: null,
    money_quote: null,
    date_quote: null,
  })
})
it('preserves history but disables changes for a corrected or deleted source', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            ...empty,
            can_edit: false,
            current: revision,
            current_head: 'revision',
            items: [revision],
          }),
        ),
    ),
  )
  render(<ReceiptPurchaseDetails id="receipt" index={0} csrfToken="csrf" />)
  await screen.findByDisplayValue('49.90')
  expect(screen.getByLabelText('USD line total 1')).toBeDisabled()
  expect(
    screen.getByRole('button', { name: 'Save purchase details' }),
  ).toBeDisabled()
  expect(
    screen.getByText(/The original source changed or was deleted/),
  ).toBeVisible()
})
