import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { AssetActions } from './AssetActions'

afterEach(() => vi.unstubAllGlobals())
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
