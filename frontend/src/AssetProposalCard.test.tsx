import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AssetProposalCard } from './AssetProposalCard'

const fields = {
  name: 'Husqvarna 525L',
  manufacturer: 'Husqvarna',
  model: '525L',
  serial: null,
  kind: 'purchase',
  quote: 'I bought a Husqvarna 525L trimmer.',
}
const proposal = {
  id: 'proposal-1',
  source_id: 'original',
  current_source_id: 'original',
  state: 'proposed',
  stale: false,
  proposed: {
    candidate: fields,
    explanation: 'A stated purchase. <script>unsafe()</script>',
  },
  reviewed: null,
  result: {},
}

describe('asset proposal review', () => {
  it('requires checked evidence and an explicit same/different choice, invalidated by edits', async () => {
    const user = userEvent.setup()
    const request = vi.fn(async (path: string, init?: RequestInit) => {
      if (path.endsWith('/preview'))
        return {
          candidates: [{ id: 'existing', name: 'Husqvarna 525L' }],
          reliable_ids: [],
        }
      if (path.endsWith('/review'))
        return {
          ...proposal,
          state: 'accepted',
          reviewed: JSON.parse(init!.body as string).fields,
          result: { asset_ids: ['existing'] },
        }
      return proposal
    })
    const open = vi.fn().mockResolvedValue(undefined)
    render(
      <AssetProposalCard id="proposal-1" request={request} onOpen={open} />,
    )
    expect(await screen.findByLabelText('Item name')).toHaveValue(
      'Husqvarna 525L',
    )
    expect(screen.getByRole('button', { name: 'Confirm asset' })).toBeDisabled()
    expect(screen.getByText(proposal.proposed.explanation)).toBeVisible()
    expect(document.querySelector('script')).toBeNull()
    await user.click(
      screen.getByRole('button', {
        name: 'Check details and possible duplicates',
      }),
    )
    expect(screen.getByRole('button', { name: 'Confirm asset' })).toBeDisabled()
    await user.selectOptions(screen.getByLabelText('Physical item'), 'existing')
    await user.clear(screen.getByLabelText('Item name'))
    await user.type(screen.getByLabelText('Item name'), 'trimmer')
    expect(screen.queryByLabelText('Physical item')).toBeNull()
    await user.click(
      screen.getByRole('button', {
        name: 'Check details and possible duplicates',
      }),
    )
    await user.selectOptions(screen.getByLabelText('Physical item'), 'existing')
    await user.click(screen.getByRole('button', { name: 'Confirm asset' }))
    expect(
      await screen.findByText(/Saved to inventory with source evidence/),
    ).toBeVisible()
    const [, init] = request.mock.calls.find(([path]) =>
      path.endsWith('/review'),
    )!
    expect(JSON.parse(init!.body as string)).toMatchObject({
      proposal_id: 'proposal-1',
      action: 'link',
      asset_id: 'existing',
      candidate_ids: ['existing'],
      fields: { name: 'trimmer' },
    })
    await user.click(
      screen.getByRole('button', { name: 'View supporting note' }),
    )
    expect(open).toHaveBeenCalledWith('original')
  })

  it('retries the identical decision after a lost response and freezes edits', async () => {
    const user = userEvent.setup()
    let reviews = 0
    const bodies: string[] = []
    const request = vi.fn(async (path: string, init?: RequestInit) => {
      if (path.endsWith('/preview')) return { candidates: [], reliable_ids: [] }
      if (path.endsWith('/review')) {
        bodies.push(init!.body as string)
        if (!reviews++) throw new TypeError('Connection lost')
        return {
          ...proposal,
          state: 'accepted',
          reviewed: fields,
          result: { asset_ids: ['new'] },
        }
      }
      return proposal
    })
    render(
      <AssetProposalCard id="proposal-1" request={request} onOpen={vi.fn()} />,
    )
    await screen.findByLabelText('Item name')
    await user.click(
      screen.getByRole('button', {
        name: 'Check details and possible duplicates',
      }),
    )
    await user.click(screen.getByRole('button', { name: 'Confirm asset' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Retry checks the same decision',
    )
    expect(screen.getByLabelText('Item name')).toBeDisabled()
    expect(
      screen.getByRole('button', { name: 'Reject proposal' }),
    ).toBeDisabled()
    await user.click(
      screen.getByRole('button', { name: 'Retry same decision' }),
    )
    expect(bodies).toHaveLength(2)
    expect(bodies[0]).toBe(bodies[1])
    expect(await screen.findByText(/Saved to inventory/)).toBeVisible()
  })

  it('rejects without inventory writes and blocks acceptance of stale notes', async () => {
    const user = userEvent.setup()
    const request = vi.fn(async (path: string, _init?: RequestInit) =>
      path.endsWith('/review')
        ? { ...proposal, state: 'rejected', stale: true }
        : { ...proposal, stale: true, current_source_id: 'newer' },
    )
    const open = vi.fn().mockResolvedValue(undefined)
    render(
      <AssetProposalCard id="proposal-1" request={request} onOpen={open} />,
    )
    expect(
      await screen.findByText(/The note has a newer correction/),
    ).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Confirm asset' })).toBeNull()
    await user.click(screen.getByRole('button', { name: 'View current note' }))
    expect(open).toHaveBeenCalledWith('newer')
    await user.click(
      screen.getByRole('button', { name: 'Reject earlier proposal' }),
    )
    expect(await screen.findByText(/Proposal rejected/)).toBeVisible()
    const body = JSON.parse(request.mock.calls[1][1]!.body as string)
    expect(body).toMatchObject({
      action: 'reject',
      fields: null,
      asset_id: null,
    })
  })
})

it('records a clear reviewed item without a separate identity choice', async () => {
  const user = userEvent.setup()
  const operations: Record<string, unknown>[] = []
  const request = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.endsWith('/review')) {
      operations.push(JSON.parse(String(init?.body)))
      return {
        ...proposal,
        state: 'accepted',
        reviewed: fields,
        result: { asset_ids: ['asset'], automatic_outcome: 'create' },
      }
    }
    return proposal
  })
  render(
    <AssetProposalCard id="proposal-1" request={request} onOpen={vi.fn()} />,
  )
  await user.click(
    await screen.findByRole('button', { name: 'Record if identity is clear' }),
  )
  await screen.findByText(/Recorded through a clear automatic identity check/)
  expect(operations[0]).toMatchObject({
    action: 'auto',
    asset_id: null,
    candidate_ids: [],
    fields,
  })
  expect(request.mock.calls.some(([path]) => path.endsWith('/preview'))).toBe(
    false,
  )
})
it('leaves an ambiguous identity pending and preserves edited fields for explicit review', async () => {
  const user = userEvent.setup()
  const request = vi.fn(async (path: string) =>
    path.endsWith('/review')
      ? {
          ...proposal,
          automatic_outcome: 'review',
          automatic_reason: 'Name similarity is ambiguous',
          automatic_check: {
            candidates: [{ id: 'existing', name: 'Existing trimmer' }],
            reliable_ids: [],
          },
        }
      : proposal,
  )
  render(
    <AssetProposalCard id="proposal-1" request={request} onOpen={vi.fn()} />,
  )
  const name = await screen.findByLabelText('Item name')
  await user.clear(name)
  await user.type(name, 'trimmer')
  await user.click(
    screen.getByRole('button', { name: 'Record if identity is clear' }),
  )
  await screen.findByText(/Identity needs your decision/)
  expect(screen.getByLabelText('Item name')).toHaveValue('trimmer')
  expect(screen.getByLabelText('Physical item')).toHaveValue('')
  expect(screen.getByRole('button', { name: 'Confirm asset' })).toBeDisabled()
})

it('freezes automatic discovery and retries its exact request after connection loss', async () => {
  const user = userEvent.setup()
  const bodies: string[] = []
  const request = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.endsWith('/review')) {
      bodies.push(String(init?.body))
      if (bodies.length === 1) throw new TypeError('connection lost')
      return {
        ...proposal,
        state: 'accepted',
        reviewed: fields,
        result: { asset_ids: ['asset'], automatic_outcome: 'create' },
      }
    }
    return proposal
  })
  render(
    <AssetProposalCard id="proposal-1" request={request} onOpen={vi.fn()} />,
  )
  await user.click(
    await screen.findByRole('button', { name: 'Record if identity is clear' }),
  )
  await screen.findByRole('button', { name: 'Retry same decision' })
  expect(screen.getByLabelText('Item name')).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Reject proposal' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Retry same decision' }))
  await screen.findByText(/Recorded through a clear automatic identity check/)
  expect(bodies).toHaveLength(2)
  expect(bodies[0]).toBe(bodies[1])
  expect(JSON.parse(bodies[1]).action).toBe('auto')
})
