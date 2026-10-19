import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ChatPhotoUpload } from './ChatPhotoUpload'
import { ChatPhotoPicker } from './ChatPhotoPicker'

afterEach(() => vi.unstubAllGlobals())
const photo = {
  id: 'private',
  filename: 'Synthetic label.jpg',
  purpose: 'photo',
}
const json = (status = 201) => new Response(JSON.stringify(photo), { status })
const file = () =>
  new File(['synthetic image'], photo.filename, { type: 'image/jpeg' })
function mount() {
  const onStart = vi.fn()
  const onSaved = vi.fn()
  const onBusy = vi.fn()
  const view = render(
    <ChatPhotoUpload
      csrfToken="csrf"
      disabled={false}
      onStart={onStart}
      onSaved={onSaved}
      onBusy={onBusy}
    />,
  )
  return { ...view, onStart, onSaved, onBusy }
}

it('uploads only on explicit action with the original bytes, CSRF and encoded name', async () => {
  const fetcher = vi.fn(async () => json())
  vi.stubGlobal('fetch', fetcher)
  const { onSaved } = mount()
  const user = userEvent.setup()
  const original = file()
  await user.upload(screen.getByLabelText('Upload a photo in Chat'), original)
  expect(fetcher).not.toHaveBeenCalled()
  await user.selectOptions(
    screen.getByLabelText('Chat photo purpose'),
    'nameplate',
  )
  await user.click(screen.getByRole('button', { name: 'Save photo privately' }))
  expect(await screen.findByText(/Photo saved privately/)).toBeVisible()
  expect(fetcher).toHaveBeenCalledTimes(1)
  expect(fetcher).toHaveBeenCalledWith(
    '/api/photos?purpose=nameplate',
    expect.objectContaining({
      method: 'POST',
      body: original,
      credentials: 'same-origin',
      cache: 'no-store',
      headers: {
        'Content-Type': 'application/octet-stream',
        'X-CSRF-Token': 'csrf',
        'X-File-Name': encodeURIComponent(original.name),
      },
    }),
  )
  expect(onSaved).toHaveBeenCalledWith(photo)
})

it.each(['large', 'type', 'empty'])(
  'refuses an invalid %s file before making a request',
  async (kind) => {
    const fetcher = vi.fn()
    vi.stubGlobal('fetch', fetcher)
    mount()
    const user = userEvent.setup({ applyAccept: false })
    const original =
      kind === 'large'
        ? new File([new Uint8Array(8 * 1024 * 1024 + 1)], 'large.jpg', {
            type: 'image/jpeg',
          })
        : new File([kind === 'empty' ? '' : 'gif'], 'invalid.jpg', {
            type: kind === 'type' ? 'image/gif' : 'image/jpeg',
          })
    await user.upload(screen.getByLabelText('Upload a photo in Chat'), original)
    await user.click(
      screen.getByRole('button', { name: 'Save photo privately' }),
    )
    expect(await screen.findByRole('alert')).toBeVisible()
    expect(fetcher).not.toHaveBeenCalled()
  },
)

it.each(['lost', 'server'])(
  'freezes the same file and purpose after an uncertain %s response',
  async (failure) => {
    const fetcher = vi
      .fn()
      .mockImplementationOnce(async () => {
        if (failure === 'lost') throw new Error('Synthetic lost response')
        return json(503)
      })
      .mockImplementationOnce(async () => json())
    vi.stubGlobal('fetch', fetcher)
    mount()
    const user = userEvent.setup()
    await user.upload(screen.getByLabelText('Upload a photo in Chat'), file())
    await user.click(
      screen.getByRole('button', { name: 'Save photo privately' }),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(
      /outcome is unknown/,
    )
    expect(screen.getByLabelText('Upload a photo in Chat')).toBeDisabled()
    expect(screen.getByLabelText('Chat photo purpose')).toBeDisabled()
    await user.click(
      screen.getByRole('button', { name: 'Retry same photo upload' }),
    )
    expect(await screen.findByText(/Photo saved privately/)).toBeVisible()
    const [first, second] = fetcher.mock.calls
    expect(second[0]).toBe(first[0])
    expect(second[1].body).toBe(first[1].body)
    expect(second[1].headers).toEqual(first[1].headers)
  },
)

it('allows correcting a rejected file without claiming an uncertain save', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => json(400)),
  )
  mount()
  const user = userEvent.setup()
  await user.upload(screen.getByLabelText('Upload a photo in Chat'), file())
  await user.click(screen.getByRole('button', { name: 'Save photo privately' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(/not accepted/)
  expect(screen.getByLabelText('Upload a photo in Chat')).toBeEnabled()
  expect(
    screen.queryByRole('button', { name: 'Retry same photo upload' }),
  ).not.toBeInTheDocument()
})

it.each([201, 503])(
  'ignores a late upload response after leaving the picker (%s)',
  async (status) => {
    let release!: (value: Response) => void
    const fetcher = vi.fn(
      (_path: string, _init?: RequestInit) =>
        new Promise<Response>((resolve) => {
          release = resolve
        }),
    )
    vi.stubGlobal('fetch', fetcher)
    const { unmount, onSaved, onBusy } = mount()
    const user = userEvent.setup()
    await user.upload(screen.getByLabelText('Upload a photo in Chat'), file())
    await user.click(
      screen.getByRole('button', { name: 'Save photo privately' }),
    )
    expect(screen.getByRole('button', { name: 'Saving photo…' })).toBeDisabled()
    unmount()
    expect(fetcher.mock.calls[0][1]?.signal?.aborted).toBe(true)
    await act(async () => release(json(status)))
    expect(onSaved).not.toHaveBeenCalled()
    expect(onBusy.mock.calls).toEqual([[true]])
  },
)

it('keeps an uploaded original unique when a later library page includes it', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === 'POST') return json()
      if (path.includes('cursor=page-two'))
        return new Response(
          JSON.stringify({
            items: [
              photo,
              photo,
              { ...photo, id: 'third', filename: 'Another.jpg' },
            ],
            next_cursor: null,
          }),
        )
      return new Response(
        JSON.stringify({
          items: [{ ...photo, id: 'first', filename: 'First.jpg' }],
          next_cursor: 'page-two',
        }),
      )
    }),
  )
  render(
    <ChatPhotoPicker
      csrfToken="csrf"
      disabled={false}
      selected={null}
      onSelect={vi.fn()}
    />,
  )
  const user = userEvent.setup()
  await user.click(
    screen.getByRole('button', { name: 'Load saved Chat photos' }),
  )
  await screen.findByRole('button', { name: 'Choose photo First.jpg' })
  await user.upload(screen.getByLabelText('Upload a photo in Chat'), file())
  await user.click(screen.getByRole('button', { name: 'Save photo privately' }))
  await screen.findByText(/Photo saved privately/)
  await user.click(
    screen.getByRole('button', { name: 'More saved Chat photos' }),
  )
  expect(
    await screen.findByRole('button', { name: 'Choose photo Another.jpg' }),
  ).toBeVisible()
  expect(
    screen.getAllByRole('button', { name: 'Choose photo Synthetic label.jpg' }),
  ).toHaveLength(1)
  expect(
    screen.getByRole('button', { name: 'Choose photo First.jpg' }),
  ).toBeVisible()
})
