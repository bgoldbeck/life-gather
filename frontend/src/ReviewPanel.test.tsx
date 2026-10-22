import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ReviewPanel } from './ReviewPanel'

afterEach(() => vi.unstubAllGlobals())
const item = {
  key: 'd:obs',
  id: 'obs',
  kind: 'identity',
  name: 'Synthetic drill',
  reason: 'Name alone is ambiguous',
  source_id: 'source',
}
const detail = {
  observation_id: 'obs',
  decision_id: 'decision',
  outcome: 'review',
  reason: item.reason,
  observation: {
    name: item.name,
    quote: 'I own a synthetic drill',
    source_id: 'source',
    quantity: 1,
    kind: 'possession',
    manufacturer: null,
    model: null,
    serial: null,
  },
  candidates: [{ id: 'asset', name: 'Earlier drill' }],
  reliable_ids: [],
}

it('leaves uncertain work pending and resolves an explicit same-item choice without AI', async () => {
  const user = userEvent.setup()
  const calls: { url: string; init?: RequestInit }[] = []
  let resolved = false
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      let result: unknown = { items: resolved ? [] : [item], next_cursor: null }
      if (url === '/api/reviews/identities/obs') result = detail
      if (url === '/api/reviews/identities/review') {
        resolved = true
        result = { outcome: 'enrich' }
      }
      return new Response(JSON.stringify(result))
    }),
  )
  render(<ReviewPanel csrfToken="csrf" />)
  await user.click(
    await screen.findByRole('button', { name: 'Synthetic drill' }),
  )
  await user.click(
    screen.getByRole('button', { name: 'Not sure — leave pending' }),
  )
  expect(
    await screen.findByText(
      'Left pending. You can return to this review later.',
    ),
  ).toBeVisible()
  expect(calls.filter((c) => c.init?.method === 'POST')).toHaveLength(0)
  await user.click(screen.getByRole('button', { name: 'Synthetic drill' }))
  await user.click(
    screen.getByLabelText(
      'Same items — choose existing records for every unit',
    ),
  )
  expect(
    screen.getByRole('button', { name: 'Confirm identity review' }),
  ).toBeDisabled()
  await user.selectOptions(
    screen.getByLabelText('Existing item for unit 1'),
    'asset',
  )
  await user.click(
    screen.getByRole('button', { name: 'Confirm identity review' }),
  )
  await screen.findByText('No pending reviews in this view.')
  const write = calls.find((c) => c.init?.method === 'POST')!
  expect(write.init?.headers).toMatchObject({ 'X-CSRF-Token': 'csrf' })
  expect(JSON.parse(String(write.init?.body))).toEqual({
    observation_id: 'obs',
    expected_decision_id: 'decision',
    action: 'link',
    asset_ids: ['asset'],
    candidate_ids: ['asset'],
  })
  expect(calls.some((c) => c.url.includes('/turns'))).toBe(false)
})

it('undoes a dismissal so the match returns to the queue', async () => {
  const user = userEvent.setup()
  const calls: { url: string; init?: RequestInit }[] = []
  let dismissed = false
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      let result: unknown = {
        items: dismissed ? [] : [item],
        next_cursor: null,
      }
      if (url === '/api/reviews/identities/obs') result = detail
      if (url === '/api/reviews/identities/review') {
        dismissed = true
        result = { id: 'obs', decision_id: 'dismissed', outcome: 'dismissed' }
      }
      if (url === '/api/reviews/identities/undo') {
        dismissed = false
        result = { id: 'obs', decision_id: 'restored', outcome: 'review' }
      }
      return new Response(JSON.stringify(result))
    }),
  )
  render(<ReviewPanel csrfToken="csrf" />)
  await user.click(
    await screen.findByRole('button', { name: 'Synthetic drill' }),
  )
  await user.click(screen.getByLabelText(/Exclude this discovery/))
  await user.click(
    screen.getByRole('button', { name: 'Confirm identity review' }),
  )
  await screen.findByText('No pending reviews in this view.')
  await user.click(screen.getByRole('button', { name: 'Undo identity review' }))
  await screen.findByText(/Review undone. The match is back in the queue/)
  const undo = calls.find((c) => c.url === '/api/reviews/identities/undo')!
  expect(undo.init?.headers).toMatchObject({ 'X-CSRF-Token': 'csrf' })
  expect(JSON.parse(String(undo.init?.body))).toEqual({
    observation_id: 'obs',
    decision_id: 'dismissed',
  })
  expect(
    await screen.findByRole('button', { name: 'Synthetic drill' }),
  ).toBeVisible()
  expect(
    screen.queryByRole('button', { name: 'Undo identity review' }),
  ).not.toBeInTheDocument()
})

it('requires distinct choices for multiple units and retries the same decision after lost response', async () => {
  const user = userEvent.setup()
  const bodies: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      let result: unknown = { items: [item], next_cursor: null }
      if (url === '/api/reviews/identities/obs')
        result = {
          ...detail,
          observation: { ...detail.observation, quantity: 2 },
          candidates: [
            { id: 'a', name: 'Drill A' },
            { id: 'b', name: 'Drill B' },
          ],
        }
      if (init?.method === 'POST') {
        bodies.push(String(init.body))
        if (bodies.length === 1) throw new TypeError('lost connection')
        result = { outcome: 'enrich' }
      }
      return new Response(JSON.stringify(result))
    }),
  )
  render(<ReviewPanel csrfToken="csrf" />)
  await user.click(
    await screen.findByRole('button', { name: 'Synthetic drill' }),
  )
  await user.click(
    screen.getByLabelText(
      'Same items — choose existing records for every unit',
    ),
  )
  await user.selectOptions(
    screen.getByLabelText('Existing item for unit 1'),
    'a',
  )
  await user.selectOptions(
    screen.getByLabelText('Existing item for unit 2'),
    'a',
  )
  expect(
    screen.getByRole('button', { name: 'Confirm identity review' }),
  ).toBeDisabled()
  await user.selectOptions(
    screen.getByLabelText('Existing item for unit 2'),
    'b',
  )
  await user.click(
    screen.getByRole('button', { name: 'Confirm identity review' }),
  )
  await user.click(
    await screen.findByRole('button', { name: 'Retry same review' }),
  )
  await screen.findByText(
    'Review saved. The queue now reflects the current records.',
  )
  expect(bodies).toHaveLength(2)
  expect(bodies[0]).toBe(bodies[1])
})

it('uses the same proposal card as Chat and refreshes after rejection', async () => {
  const user = userEvent.setup()
  let rejected = false
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      let result: unknown = {
        items: rejected
          ? []
          : [{ ...item, kind: 'proposal', key: 'p:proposal', id: 'proposal' }],
        next_cursor: null,
      }
      const proposal = {
        id: 'proposal',
        source_id: 'source',
        current_source_id: 'source',
        state: rejected ? 'rejected' : 'proposed',
        stale: false,
        proposed: {
          candidate: {
            name: 'Synthetic drill',
            manufacturer: null,
            model: null,
            serial: null,
            kind: 'possession',
            quote: 'I own a drill',
          },
          explanation: 'Review first',
        },
        reviewed: null,
        result: {},
      }
      if (url === '/api/chat/asset-proposals/proposal') result = proposal
      else if (
        url === '/api/chat/asset-proposals/review' &&
        init?.method === 'POST'
      ) {
        rejected = true
        result = { ...proposal, state: 'rejected' }
      }
      return new Response(JSON.stringify(result))
    }),
  )
  render(<ReviewPanel csrfToken="csrf" />)
  await user.click(
    await screen.findByRole('button', { name: 'Synthetic drill' }),
  )
  await user.click(
    await screen.findByRole('button', { name: 'Reject proposal' }),
  )
  await waitFor(() =>
    expect(screen.getByText('No pending reviews in this view.')).toBeVisible(),
  )
})
