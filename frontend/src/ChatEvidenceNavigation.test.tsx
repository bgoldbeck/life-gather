import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ChatPanel } from './ChatPanel'

vi.mock('./ReceiptProposalCard', () => ({
  ReceiptProposalCard: ({ id }: { id: string }) => (
    <section aria-label="Receipt review fixture">{id}</section>
  ),
}))
vi.mock('./AssetProposalCard', () => ({
  AssetProposalCard: ({ id }: { id: string }) => (
    <section aria-label="Asset proposal fixture">{id}</section>
  ),
}))
afterEach(() => vi.unstubAllGlobals())
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status })
function deferred() {
  let release!: (response: Response) => void
  const promise = new Promise<Response>((resolve) => {
    release = resolve
  })
  return { promise, release }
}
function turn(id: string) {
  return {
    id: 'turn-' + id,
    request_id: id,
    mode: 'search',
    text: id + ' question',
    state: 'complete',
    result: {
      text: id + ' reply',
      sources: [{ id: 'source-' + id, text: id + ' source' }],
      receipt_proposal_id: 'receipt-' + id,
      proposal_id: 'proposal-' + id,
    },
  }
}
function server(source: (url: string) => Promise<Response>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.startsWith('/api/chat/sources/')) return source(url)
      if (url === '/api/chat/conversations')
        return json({
          items: [
            { id: 'old', title: 'Original conversation' },
            { id: 'other', title: 'Other conversation' },
          ],
          next_cursor: null,
        })
      if (url === '/api/chat/conversations/old/turns')
        return json({ items: [turn('old')], next_cursor: null })
      if (url === '/api/chat/conversations/other/turns')
        return json({ items: [turn('other')], next_cursor: null })
      if (url === '/api/chat/preferences')
        return json({ credential_id: '', model: '' })
      if (url === '/api/chat/usage') return json({ requests: 0 })
      return json({ items: [], allow_external_ai: false })
    }),
  )
}

it.each([200, 500])(
  'ignores late source results (%s) after starting a new conversation',
  async (status) => {
    const user = userEvent.setup()
    const late = deferred()
    server(() => late.promise)
    render(<ChatPanel csrfToken="csrf" />)
    await user.click(
      await screen.findByRole('button', { name: 'Original conversation' }),
    )
    await user.click(
      await screen.findByRole('button', { name: 'Source 1: old source' }),
    )
    await user.click(screen.getByRole('button', { name: 'New conversation' }))
    await act(async () =>
      late.release(
        json(
          { id: 'source-old', text: 'Late old citation.', next_offset: null },
          status,
        ),
      ),
    )
    expect(
      screen.queryByRole('region', { name: 'Original evidence' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByText('Late old citation.')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  },
)

it('keeps the new conversation citation loading when an older read completes', async () => {
  const user = userEvent.setup()
  const old = deferred()
  const current = deferred()
  server((url) => (url.includes('source-old') ? old.promise : current.promise))
  render(<ChatPanel csrfToken="csrf" />)
  await user.click(
    await screen.findByRole('button', { name: 'Original conversation' }),
  )
  await user.click(
    await screen.findByRole('button', { name: 'Source 1: old source' }),
  )
  await user.click(screen.getByRole('button', { name: 'Other conversation' }))
  await user.click(
    await screen.findByRole('button', { name: 'Source 1: other source' }),
  )
  await act(async () =>
    old.release(
      json({ id: 'source-old', text: 'Late old citation.', next_offset: null }),
    ),
  )
  expect(
    screen.getByRole('button', { name: 'Source 1: other source' }),
  ).toBeDisabled()
  expect(screen.queryByText('Late old citation.')).not.toBeInTheDocument()
  await act(async () =>
    current.release(
      json({
        id: 'source-other',
        text: 'Correct current citation.',
        next_offset: null,
      }),
    ),
  )
  expect(await screen.findByText('Correct current citation.')).toBeVisible()
})

it('keeps evidence closed when an in-flight source page finishes', async () => {
  const user = userEvent.setup()
  const late = deferred()
  server(async (url) =>
    url.endsWith('offset=20')
      ? late.promise
      : json({ id: 'source-old', text: 'First source page.', next_offset: 20 }),
  )
  render(<ChatPanel csrfToken="csrf" />)
  await user.click(
    await screen.findByRole('button', { name: 'Original conversation' }),
  )
  await user.click(
    await screen.findByRole('button', { name: 'Source 1: old source' }),
  )
  await screen.findByText('First source page.')
  await user.click(screen.getByRole('button', { name: 'Next source page' }))
  await user.click(screen.getByRole('button', { name: 'Close evidence' }))
  await act(async () =>
    late.release(
      json({ id: 'source-old', text: 'Late next page.', next_offset: null }),
    ),
  )
  expect(
    screen.queryByRole('region', { name: 'Original evidence' }),
  ).not.toBeInTheDocument()
  expect(screen.queryByText('Late next page.')).not.toBeInTheDocument()
})

it.each(['New conversation', 'Other conversation'])(
  'clears old receipt and asset review panels on %s',
  async (destination) => {
    const user = userEvent.setup()
    server(async () =>
      json({ id: 'source-old', text: 'Source.', next_offset: null }),
    )
    render(<ChatPanel csrfToken="csrf" />)
    await user.click(
      await screen.findByRole('button', { name: 'Original conversation' }),
    )
    await user.click(
      await screen.findByRole('button', { name: 'View receipt review' }),
    )
    await user.click(
      screen.getByRole('button', { name: 'View asset proposal' }),
    )
    expect(
      screen.getByRole('region', { name: 'Receipt review fixture' }),
    ).toHaveTextContent('receipt-old')
    expect(
      screen.getByRole('region', { name: 'Asset proposal fixture' }),
    ).toHaveTextContent('proposal-old')
    await user.click(screen.getByRole('button', { name: destination }))
    expect(
      screen.queryByRole('region', { name: 'Receipt review fixture' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('region', { name: 'Asset proposal fixture' }),
    ).not.toBeInTheDocument()
  },
)
