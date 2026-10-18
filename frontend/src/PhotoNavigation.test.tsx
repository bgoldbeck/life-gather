import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { PhotosPanel } from './PhotosPanel'

afterEach(() => vi.unstubAllGlobals())
const photo = {
  id: 'first',
  filename: 'first.jpg',
  purpose: 'photo',
  size: 1000,
  width: 20,
  height: 10,
  updated_at: 5,
  source_id: 'source-first',
  deleted_at: null,
}
const other = {
  ...photo,
  id: 'other',
  filename: 'other.jpg',
  source_id: 'source-other',
}
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status })
function deferred() {
  let release!: (response: Response) => void
  const promise = new Promise<Response>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

it('keeps a newly refreshed upload when initial gallery metadata arrives late', async () => {
  const user = userEvent.setup()
  const metadata = deferred()
  let uploaded = false
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/credentials?limit=100') return metadata.promise
      if (url.startsWith('/api/photos?') && init?.method === 'POST') {
        uploaded = true
        return json(photo)
      }
      if (url.startsWith('/api/photos?'))
        return json({ items: uploaded ? [photo] : [], next_cursor: null })
      return json({ allow_external_ai: false })
    }),
  )
  render(<PhotosPanel csrfToken="csrf" assetId="asset" />)
  await user.upload(
    screen.getByLabelText('Photo file'),
    new File(['synthetic'], 'first.jpg', { type: 'image/jpeg' }),
  )
  await user.click(
    screen.getByRole('button', { name: 'Upload privately to this item' }),
  )
  await screen.findByText('Photo saved privately. No AI request was made.')
  await act(async () => metadata.release(json({ items: [] })))
  expect(screen.getByRole('button', { name: /first.jpg/ })).toBeInTheDocument()
  expect(
    screen.queryByText('No photos saved here yet.'),
  ).not.toBeInTheDocument()
})

it.each([200, 500])(
  'ignores a late transcription response (%s) after another photo is selected',
  async (status) => {
    const user = userEvent.setup()
    const source = deferred()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url === '/api/chat/sources/source-first') return source.promise
        if (url.startsWith('/api/photos?'))
          return json({ items: [photo, other], next_cursor: null })
        return json({ items: [], allow_external_ai: false })
      }),
    )
    render(<PhotosPanel csrfToken="csrf" />)
    await user.click(await screen.findByRole('button', { name: /first.jpg/ }))
    await user.click(
      screen.getByRole('button', { name: 'View saved transcription' }),
    )
    await user.click(screen.getByRole('button', { name: /other.jpg/ }))
    await act(async () =>
      source.release(
        json(
          { id: 'source-first', text: 'Late text from the previous photo.' },
          status,
        ),
      ),
    )
    expect(
      screen.getByRole('heading', { name: 'other.jpg' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByText('Late text from the previous photo.'),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'View saved transcription' }),
    ).toBeEnabled()
  },
)

it('does not reopen a transcription after evidence inspection is closed', async () => {
  const user = userEvent.setup()
  const late = deferred()
  let reads = 0
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url === '/api/chat/sources/source-first')
        return ++reads === 1
          ? json({
              id: 'source-first',
              text: 'Original synthetic transcription.',
            })
          : late.promise
      if (url.startsWith('/api/photos?'))
        return json({ items: [photo], next_cursor: null })
      return json({ items: [], allow_external_ai: false })
    }),
  )
  render(<PhotosPanel csrfToken="csrf" />)
  await user.click(await screen.findByRole('button', { name: /first.jpg/ }))
  await user.click(
    screen.getByRole('button', { name: 'View saved transcription' }),
  )
  await screen.findByText('Original synthetic transcription.')
  await user.click(
    screen.getByRole('button', { name: 'View saved transcription' }),
  )
  await user.click(screen.getByRole('button', { name: 'Close evidence' }))
  await act(async () =>
    late.release(
      json({ id: 'source-first', text: 'Late reopened transcription.' }),
    ),
  )
  expect(
    screen.queryByRole('region', { name: 'Original evidence' }),
  ).not.toBeInTheDocument()
  expect(
    screen.queryByText('Late reopened transcription.'),
  ).not.toBeInTheDocument()
})

it('ignores old pagination after a fresh upload reload resets the gallery', async () => {
  const user = userEvent.setup()
  const late = deferred()
  let uploaded = false
  const fresh = { ...photo, id: 'fresh', filename: 'fresh.jpg' }
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('&cursor=old-page')) return late.promise
      if (url.startsWith('/api/photos?') && init?.method === 'POST') {
        uploaded = true
        return json(fresh)
      }
      if (url.startsWith('/api/photos?'))
        return json({
          items: uploaded ? [photo, fresh] : [photo],
          next_cursor: uploaded ? null : 'old-page',
        })
      return json({ items: [], allow_external_ai: false })
    }),
  )
  render(<PhotosPanel csrfToken="csrf" />)
  await user.click(await screen.findByRole('button', { name: 'More photos' }))
  await user.upload(
    screen.getByLabelText('Photo file'),
    new File(['synthetic'], 'fresh.jpg', { type: 'image/jpeg' }),
  )
  await user.click(screen.getByRole('button', { name: 'Upload privately' }))
  await screen.findByText('Photo saved privately. No AI request was made.')
  await act(async () =>
    late.release(json({ items: [other], next_cursor: null })),
  )
  expect(screen.getByRole('button', { name: /fresh.jpg/ })).toBeInTheDocument()
  expect(
    screen.queryByRole('button', { name: /other.jpg/ }),
  ).not.toBeInTheDocument()
})
