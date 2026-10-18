import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { AssetReplacement } from './AssetReplacement'

afterEach(() => vi.unstubAllGlobals())

function fixture({
  lose = false,
  withdrawId,
  reject = false,
  reloadFails = false,
}: {
  lose?: boolean
  withdrawId?: string
  reject?: boolean
  reloadFails?: boolean
} = {}) {
  const writes: { path: string; body: Record<string, unknown> }[] = []
  const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.startsWith('/api/assets?'))
      return new Response(
        JSON.stringify({
          items: [
            { id: 'original', name: 'Original' },
            { id: 'replacement', name: 'Replacement drill' },
          ],
          next_cursor: null,
        }),
      )
    writes.push({ path, body: JSON.parse(String(init?.body)) })
    if (lose && writes.length === 1) throw new Error('Synthetic response loss')
    return new Response(JSON.stringify({ id: 'saved' }), {
      status: reject ? 409 : 200,
    })
  })
  vi.stubGlobal('fetch', fetcher)
  const changed = reloadFails
    ? vi
        .fn()
        .mockRejectedValueOnce(new Error('Synthetic reload loss'))
        .mockResolvedValue(undefined)
    : vi.fn().mockResolvedValue(undefined)
  render(
    <AssetReplacement
      assetId="original"
      assetName="Original drill"
      head="head"
      withdrawId={withdrawId}
      csrfToken="csrf"
      onChanged={changed}
      onOpen={vi.fn()}
    />,
  )
  return { user: userEvent.setup(), writes, fetcher, changed }
}

async function choose(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Find replacements' }))
  await user.selectOptions(
    screen.getByLabelText('Item that replaced this one'),
    'replacement',
  )
}

it('records the explicit replacement direction and leaves an unknown date absent', async () => {
  const { user, writes } = fixture()
  expect(
    screen.getByRole('button', { name: 'Record replacement link' }),
  ).toBeDisabled()
  await choose(user)
  expect(
    screen.getByText(/Record: Replacement drill .* replaced Original drill/),
  ).toBeInTheDocument()
  expect(
    screen.queryByRole('option', { name: /Original ·/ }),
  ).not.toBeInTheDocument()
  await user.type(
    screen.getByLabelText('Replacement explanation'),
    'This new drill replaced my original drill.',
  )
  expect(writes).toHaveLength(0)
  await user.click(
    screen.getByRole('button', { name: 'Record replacement link' }),
  )
  expect(writes[0]).toMatchObject({
    path: '/api/assets/replacements/record',
    body: {
      asset_id: 'original',
      target_asset_id: 'replacement',
      expected_action_id: 'head',
      note: 'This new drill replaced my original drill.',
      event_date: null,
    },
  })
})

it('preserves the exact dated request and freezes inputs after a lost response', async () => {
  const { user, writes } = fixture({ lose: true })
  await choose(user)
  await user.type(
    screen.getByLabelText('Replacement explanation'),
    'Explicit dated replacement.',
  )
  await user.type(
    screen.getByLabelText('Replacement date, if known'),
    '2025-01-02',
  )
  await user.click(
    screen.getByRole('button', { name: 'Record replacement link' }),
  )
  expect(await screen.findByRole('status')).toHaveTextContent('Connection lost')
  expect(screen.getByLabelText('Replacement explanation')).toBeDisabled()
  expect(screen.getByLabelText('Find replacement item')).toBeDisabled()
  await user.click(
    screen.getByRole('button', { name: 'Retry same replacement change' }),
  )
  expect(writes).toHaveLength(2)
  expect(writes[0]).toEqual(writes[1])
  expect(writes[0]?.body.event_date).toBe('2025-01-02')
})

it('clears hidden replacement selections when the search changes', async () => {
  const { user, writes } = fixture()
  await choose(user)
  await user.type(
    screen.getByLabelText('Replacement explanation'),
    'Keep my explanation.',
  )
  await user.type(
    screen.getByLabelText('Find replacement item'),
    'Different item',
  )
  expect(screen.getByLabelText('Item that replaced this one')).toHaveValue('')
  expect(
    screen.getByRole('button', { name: 'Record replacement link' }),
  ).toBeDisabled()
  expect(screen.getByLabelText('Replacement explanation')).toHaveValue(
    'Keep my explanation.',
  )
  expect(writes).toHaveLength(0)
})

it('reports refused replacement changes without clearing the draft', async () => {
  const { user } = fixture({ reject: true })
  await choose(user)
  await user.type(
    screen.getByLabelText('Replacement explanation'),
    'Keep this draft.',
  )
  await user.click(
    screen.getByRole('button', { name: 'Record replacement link' }),
  )
  expect(await screen.findByRole('status')).toHaveTextContent('refused')
  expect(screen.getByLabelText('Replacement explanation')).toHaveValue(
    'Keep this draft.',
  )
})

it('withdraws the recorded link and reloads without repeating a successful write', async () => {
  const { user, writes, changed } = fixture({
    withdrawId: 'original-action',
    reloadFails: true,
  })
  await user.type(
    screen.getByLabelText('Replacement explanation'),
    'I selected the wrong physical item.',
  )
  await user.click(
    screen.getByRole('button', { name: 'Withdraw latest replacement link' }),
  )
  expect(writes[0]).toMatchObject({
    path: '/api/assets/replacements/withdraw',
    body: {
      action_id: 'original-action',
      note: 'I selected the wrong physical item.',
    },
  })
  expect(await screen.findByRole('status')).toHaveTextContent('change saved')
  expect(
    screen.getByRole('button', { name: 'Withdraw latest replacement link' }),
  ).toBeDisabled()
  await user.click(
    screen.getByRole('button', { name: 'Reload saved replacement' }),
  )
  expect(changed).toHaveBeenCalledTimes(2)
  expect(writes).toHaveLength(1)
})
