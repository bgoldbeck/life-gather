import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import {
  ConsolidationHistory,
  type IdentityChoice,
} from './ConsolidationHistory'

afterEach(() => vi.unstubAllGlobals())
const choice: IdentityChoice = {
  id: 'choice',
  primary_name: 'Manual mower',
  secondary_name: 'Receipt mower',
  source_id: 'explanation',
  recorded_at: 1000000,
  superseded_at: 2000000,
  reverse_source_id: 'reversal',
}

it('opens both preserved explanations and pages without duplicating choices', async () => {
  const open = vi.fn(async () => {})
  const fetcher = vi.fn(
    async () =>
      new Response(
        JSON.stringify({
          identity_history: [
            choice,
            {
              ...choice,
              id: 'older',
              superseded_at: null,
              reverse_source_id: null,
            },
          ],
          next_identity_cursor: null,
        }),
      ),
  )
  vi.stubGlobal('fetch', fetcher)
  render(
    <ConsolidationHistory
      assetId="asset"
      initial={[choice]}
      cursor="choice"
      csrfToken="csrf"
      onOpen={open}
    />,
  )
  const user = userEvent.setup()
  await user.click(screen.getByText('Consolidation history'))
  await user.click(
    screen.getByRole('button', { name: 'View identity explanation' }),
  )
  await user.click(
    screen.getByRole('button', { name: 'View reversal explanation' }),
  )
  expect(open.mock.calls).toEqual([['explanation'], ['reversal']])
  await user.click(
    screen.getByRole('button', { name: 'More identity history' }),
  )
  expect(await screen.findByText(/Active identity choice/)).toBeVisible()
  expect(screen.getAllByRole('listitem')).toHaveLength(2)
  expect(fetcher).toHaveBeenCalledWith(
    '/api/assets/asset?identity_cursor=choice',
    expect.objectContaining({ credentials: 'same-origin', cache: 'no-store' }),
  )
  expect(
    screen.queryByRole('button', { name: 'More identity history' }),
  ).not.toBeInTheDocument()
})

it('keeps history on a failed read and retries the same cursor', async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(new Response('', { status: 503 }))
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({ identity_history: [], next_identity_cursor: null }),
      ),
    )
  vi.stubGlobal('fetch', fetcher)
  render(
    <ConsolidationHistory
      assetId="asset"
      initial={[choice]}
      cursor="choice"
      csrfToken="csrf"
      onOpen={vi.fn()}
    />,
  )
  const user = userEvent.setup()
  await user.click(screen.getByText('Consolidation history'))
  await user.click(
    screen.getByRole('button', { name: 'More identity history' }),
  )
  expect(await screen.findByRole('alert')).toHaveTextContent('Try again')
  expect(screen.getAllByRole('listitem')).toHaveLength(1)
  await user.click(
    screen.getByRole('button', { name: 'More identity history' }),
  )
  expect(fetcher.mock.calls[0]).toEqual(fetcher.mock.calls[1])
})

it('freezes duplicate reads and discards a response after unmount', async () => {
  let finish!: (value: Response) => void
  const fetcher = vi.fn(
    () =>
      new Promise<Response>((resolve) => {
        finish = resolve
      }),
  )
  vi.stubGlobal('fetch', fetcher)
  const view = render(
    <ConsolidationHistory
      assetId="asset"
      initial={[choice]}
      cursor="choice"
      csrfToken="csrf"
      onOpen={vi.fn()}
    />,
  )
  fireEvent.click(screen.getByText('Consolidation history'))
  const button = screen.getByRole('button', { name: 'More identity history' })
  fireEvent.click(button)
  fireEvent.click(button)
  expect(fetcher).toHaveBeenCalledOnce()
  expect(button).toBeDisabled()
  view.unmount()
  await act(async () =>
    finish(
      new Response(
        JSON.stringify({ identity_history: [], next_identity_cursor: null }),
      ),
    ),
  )
})
