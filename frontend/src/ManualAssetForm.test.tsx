import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ManualAssetForm } from './ManualAssetForm'

afterEach(() => vi.unstubAllGlobals())
const result = {
  asset: { id: 'asset', name: 'Synthetic truck' },
  source_id: 'source',
  created: true,
}
const props = () => ({
  csrfToken: 'csrf',
  onSaved: vi.fn(async () => {}),
  onOpen: vi.fn(async () => {}),
  onCancel: vi.fn(),
})
async function enter() {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Asset name'), 'Synthetic truck')
  await user.click(screen.getByLabelText('I currently own this item'))
  return user
}
it('saves manual input without AI and retains an uncertain request for safe retry', async () => {
  const callbacks = props()
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ candidates: [], reliable_ids: [] })),
    )
    .mockRejectedValueOnce(new Error('connection lost'))
    .mockResolvedValueOnce(new Response(JSON.stringify(result)))
  vi.stubGlobal('fetch', fetcher)
  render(<ManualAssetForm {...callbacks} />)
  const user = await enter()
  await user.type(screen.getByLabelText('Notes'), 'My own entry')
  await user.click(screen.getByRole('button', { name: 'Save asset' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('uncertain')
  expect(screen.getByLabelText('Asset name')).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Retry same save' }))
  expect(callbacks.onSaved).toHaveBeenCalledWith(result)
  expect(fetcher.mock.calls[1][1].body).toBe(fetcher.mock.calls[2][1].body)
  const body = JSON.parse(fetcher.mock.calls[1][1].body)
  expect(body.ownership_confirmed).toBe(true)
  expect(body.notes).toBe('My own entry')
  expect(fetcher.mock.calls[1][1].headers['X-CSRF-Token']).toBe('csrf')
})
it('requires an explicit duplicate choice and prevents creating a serial duplicate', async () => {
  const callbacks = props()
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          candidates: [
            { id: 'existing', name: 'Existing truck', can_link: true },
          ],
          reliable_ids: ['existing'],
        }),
      ),
    )
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ ...result, created: false })),
    )
  vi.stubGlobal('fetch', fetcher)
  render(<ManualAssetForm {...callbacks} />)
  const user = await enter()
  await user.click(screen.getByRole('button', { name: 'Save asset' }))
  expect(await screen.findByText(/Matching identifier/)).toBeVisible()
  expect(fetcher).toHaveBeenCalledTimes(1)
  expect(
    screen.queryByRole('button', { name: 'Create a separate item' }),
  ).not.toBeInTheDocument()
  await user.click(
    screen.getByRole('button', { name: 'Add information to Existing truck' }),
  )
  expect(JSON.parse(fetcher.mock.calls[1][1].body)).toMatchObject({
    action: 'link',
    asset_id: 'existing',
    candidate_ids: ['existing'],
  })
  expect(callbacks.onSaved).toHaveBeenCalledTimes(1)
})
it('cancels a duplicate preview when the form unmounts without saving anything', async () => {
  let finish: (value: Response) => void = () => {}
  const fetcher = vi.fn(
    (_url: string, _init: RequestInit) =>
      new Promise<Response>((resolve) => {
        finish = resolve
      }),
  )
  vi.stubGlobal('fetch', fetcher)
  const callbacks = props()
  const view = render(<ManualAssetForm {...callbacks} />)
  const user = await enter()
  await user.click(screen.getByRole('button', { name: 'Save asset' }))
  view.unmount()
  expect(fetcher.mock.calls[0][1].signal!.aborted).toBe(true)
  await act(async () =>
    finish(new Response(JSON.stringify({ candidates: [], reliable_ids: [] }))),
  )
  expect(fetcher).toHaveBeenCalledTimes(1)
  expect(callbacks.onSaved).not.toHaveBeenCalled()
})
