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
it('copies source suggestions into an editable draft without saving until review', async () => {
  const user = userEvent.setup()
  const saves: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/save')) {
        saves.push(JSON.parse(String(init?.body)))
        return new Response(JSON.stringify(revision))
      }
      return new Response(
        JSON.stringify({
          ...empty,
          suggestions: {
            line_total: revision.line_total,
            money_quote: revision.money_quote,
            purchase_date: revision.purchase_date,
            date_quote: revision.date_quote,
          },
        }),
      )
    }),
  )
  render(<ReceiptPurchaseDetails id="receipt" index={0} csrfToken="csrf" />)
  await user.click(
    await screen.findByRole('button', { name: 'Use source suggestions' }),
  )
  expect(screen.getByLabelText('USD line total 1')).toHaveValue('49.90')
  expect(screen.getByLabelText('Purchase date 1')).toHaveValue('2026-10-18')
  expect(saves).toHaveLength(0)
  await user.click(
    screen.getByRole('button', { name: 'Save purchase details' }),
  )
  expect(saves).toEqual([
    expect.objectContaining({ line_total: '49.90', expected_head: null }),
  ])
})
it('preserves an explicit non-USD currency in suggestions and saved history', async () => {
  const user = userEvent.setup()
  const saves: Record<string, unknown>[] = []
  const euro = {
    ...revision,
    currency: 'EUR',
    money_quote: revision.money_quote.replace('USD', 'EUR'),
  }
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/save')) {
        saves.push(JSON.parse(String(init?.body)))
        return new Response(JSON.stringify(euro))
      }
      return new Response(JSON.stringify({ ...empty, suggestions: euro }))
    }),
  )
  render(<ReceiptPurchaseDetails id="receipt" index={0} csrfToken="csrf" />)
  await user.click(
    await screen.findByRole('button', { name: 'Use source suggestions' }),
  )
  expect(screen.getByLabelText('Currency 1')).toHaveValue('EUR')
  expect(screen.getByLabelText('EUR line total 1')).toHaveValue('49.90')
  await user.click(
    screen.getByRole('button', { name: 'Save purchase details' }),
  )
  await screen.findByText('Line total: EUR 49.90 · Purchase date: 2026-10-18')
  expect(saves[0]).toMatchObject({ currency: 'EUR', line_total: '49.90' })
})
it('copies a grounded AI suggestion with its doubts into a reviewed draft', async () => {
  const user = userEvent.setup()
  const posts: { url: string; body: Record<string, unknown> }[] = []
  const line = 'Acme Drill Qty: 2   $349.00'
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST' && init.body)
        posts.push({ url, body: JSON.parse(String(init.body)) })
      if (url.startsWith('/api/credentials'))
        return new Response(
          JSON.stringify({
            items: [
              { id: 'ai-1', kind: 'ai', provider: 'openai', label: 'Mine' },
            ],
          }),
        )
      if (url === '/api/settings')
        return new Response(JSON.stringify({ allow_external_ai: true }))
      if (url === '/api/chat/preferences')
        return new Response(
          JSON.stringify({ credential_id: 'ai-1', model: 'fixture-model' }),
        )
      if (url.endsWith('/suggest'))
        return new Response(
          JSON.stringify({
            provider: 'openai',
            model: 'fixture-model',
            suggestion: {
              line_total: '349.00',
              currency: null,
              money_quote: line,
              purchase_date: '2026-10-11',
              date_quote: 'Date: 10/11/2026',
            },
            ambiguities: [
              {
                field: 'currency',
                message:
                  'A bare $ can mean USD, CAD or AUD; confirm the currency',
              },
            ],
            notes: 'Bare dollar sign.',
          }),
        )
      if (url.endsWith('/save'))
        return new Response(
          JSON.stringify({
            ...revision,
            line_total: '349.00',
            total_minor: 34900,
            money_quote: line,
            purchase_date: '2026-10-11',
            date_quote: 'Date: 10/11/2026',
            basis: 'reviewed',
          }),
        )
      return new Response(JSON.stringify(empty))
    }),
  )
  render(<ReceiptPurchaseDetails id="receipt" index={0} csrfToken="csrf" />)
  await user.click(
    await screen.findByRole('button', { name: 'Suggest with AI…' }),
  )
  await user.click(
    await screen.findByRole('button', { name: 'Get AI suggestions' }),
  )
  expect(posts.at(-1)).toEqual({
    url: '/api/receipts/details/suggest',
    body: {
      receipt_id: 'receipt',
      index: 0,
      credential_id: 'ai-1',
      model: 'fixture-model',
    },
  })
  expect(
    await screen.findByText(/A bare \$ can mean USD, CAD or AUD/),
  ).toBeVisible()
  await user.click(
    screen.getByRole('button', { name: 'Copy AI suggestion into draft' }),
  )
  expect(screen.getByLabelText('Unknown currency line total 1')).toHaveValue(
    '349.00',
  )
  const save = screen.getByRole('button', { name: 'Save purchase details' })
  // The currency stays unknown until a person chooses it.
  expect(save).toBeDisabled()
  await user.selectOptions(screen.getByLabelText('Currency 1'), 'CAD')
  await user.click(save)
  await screen.findByText(/reviewed reading/)
  expect(posts.at(-1)?.body).toEqual(
    expect.objectContaining({
      currency: 'CAD',
      line_total: '349.00',
      money_quote: line,
      purchase_date: '2026-10-11',
      basis: 'reviewed',
    }),
  )
})
