import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ExistingPhotoLink } from './ExistingPhotoLink'
import { PhotosPanel } from './PhotosPanel'

afterEach(() => vi.unstubAllGlobals())
const photo = {
  id: 'photo-original',
  filename: 'receipt.jpg',
  purpose: 'receipt',
  updated_at: 5,
  size: 1000,
  width: 200,
  height: 100,
  source_id: null,
  deleted_at: null,
}

function fixture({
  lose = false,
  reject = false,
  reloadFails = false,
}: { lose?: boolean; reject?: boolean; reloadFails?: boolean } = {}) {
  const writes: string[] = []
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.startsWith('/api/photos?'))
      return new Response(JSON.stringify({ items: [photo], next_cursor: null }))
    writes.push(String(init?.body))
    if (lose && writes.length === 1) throw new Error('Synthetic lost response')
    return new Response(JSON.stringify({ ...photo, updated_at: 6 }), {
      status: reject ? 409 : 200,
    })
  })
  vi.stubGlobal('fetch', fetcher)
  const linked = reloadFails
    ? vi
        .fn()
        .mockRejectedValueOnce(new Error('Synthetic reload error'))
        .mockResolvedValue(undefined)
    : vi.fn().mockResolvedValue(undefined)
  const locked = vi.fn()
  render(
    <ExistingPhotoLink
      assetId="target"
      csrfToken="csrf"
      disabled={false}
      onLinked={linked}
      onLockedChange={locked}
    />,
  )
  return { user: userEvent.setup(), writes, fetcher, linked, locked }
}
async function choose(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Load saved photos' }))
  await user.click(await screen.findByRole('button', { name: /receipt.jpg/ }))
}

it('loads only on request, requires an explicit selection and links metadata without uploading bytes', async () => {
  const { user, fetcher, writes, linked } = fixture()
  expect(fetcher).not.toHaveBeenCalled()
  expect(
    screen.getByRole('button', { name: 'Link selected photo to this item' }),
  ).toBeDisabled()
  await choose(user)
  await user.click(
    screen.getByRole('button', { name: 'Link selected photo to this item' }),
  )
  expect(JSON.parse(writes[0]!)).toEqual({
    photo_id: photo.id,
    asset_id: 'target',
    expected_updated_at: 5,
  })
  expect(fetcher).toHaveBeenLastCalledWith(
    '/api/photos/attach',
    expect.objectContaining({
      headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf' }),
    }),
  )
  expect(linked).toHaveBeenCalledTimes(1)
  expect(await screen.findByRole('status')).toHaveTextContent(
    'No AI request was made',
  )
})

it('freezes selection and retries the identical link after response loss', async () => {
  const { user, writes, locked } = fixture({ lose: true })
  await choose(user)
  await user.click(
    screen.getByRole('button', { name: 'Link selected photo to this item' }),
  )
  expect(await screen.findByRole('status')).toHaveTextContent('Connection lost')
  expect(screen.getByRole('button', { name: /receipt.jpg/ })).toBeDisabled()
  expect(
    screen.getByRole('button', { name: 'Load saved photos' }),
  ).toBeDisabled()
  expect(locked).toHaveBeenLastCalledWith(true)
  await user.click(
    screen.getByRole('button', { name: 'Retry same photo link' }),
  )
  expect(writes).toHaveLength(2)
  expect(writes[0]).toBe(writes[1])
  expect(locked).toHaveBeenLastCalledWith(false)
})

it('clears refused stale selection and requires a refreshed photo choice', async () => {
  const { user, linked } = fixture({ reject: true })
  await choose(user)
  await user.click(
    screen.getByRole('button', { name: 'Link selected photo to this item' }),
  )
  expect(await screen.findByRole('status')).toHaveTextContent('refused')
  expect(
    screen.getByRole('button', { name: 'Link selected photo to this item' }),
  ).toBeDisabled()
  expect(linked).not.toHaveBeenCalled()
})

it('retries a failed gallery reload without repeating the saved link', async () => {
  const { user, linked, writes } = fixture({ reloadFails: true })
  await choose(user)
  await user.click(
    screen.getByRole('button', { name: 'Link selected photo to this item' }),
  )
  expect(await screen.findByRole('status')).toHaveTextContent(
    'Photo link saved',
  )
  expect(
    screen.getByRole('button', { name: 'Link selected photo to this item' }),
  ).toBeDisabled()
  await user.click(
    screen.getByRole('button', { name: 'Reload linked gallery' }),
  )
  expect(linked).toHaveBeenCalledTimes(2)
  expect(writes).toHaveLength(1)
})

it('refreshes the receiving item gallery while preserving the same private original', async () => {
  const user = userEvent.setup()
  let linked = false
  const paths: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      paths.push(url)
      if (url === '/api/photos/attach') {
        linked = true
        return new Response(JSON.stringify({ ...photo, updated_at: 6 }))
      }
      if (url.startsWith('/api/photos?limit=5'))
        return new Response(
          JSON.stringify({ items: [photo], next_cursor: null }),
        )
      if (url.startsWith('/api/photos?asset_id=target'))
        return new Response(
          JSON.stringify({
            items: linked ? [{ ...photo, updated_at: 6 }] : [],
            next_cursor: null,
          }),
        )
      return new Response(
        JSON.stringify({ items: [], allow_external_ai: false }),
      )
    }),
  )
  render(<PhotosPanel assetId="target" csrfToken="csrf" />)
  await screen.findByText('No photos saved here yet.')
  await user.click(screen.getByText('Use a photo already saved'))
  await user.click(screen.getByRole('button', { name: 'Load saved photos' }))
  await user.click(await screen.findByRole('button', { name: /receipt.jpg/ }))
  await user.click(
    screen.getByRole('button', { name: 'Link selected photo to this item' }),
  )
  const chooser = screen.getByRole('region', {
    name: 'Link an existing private photo',
  })
  expect(within(chooser).getByRole('status')).toHaveTextContent('Photo linked')
  expect(screen.getAllByRole('button', { name: /receipt.jpg/ })).toHaveLength(2)
  expect(paths.filter((path) => path === '/api/photos/attach')).toHaveLength(1)
  expect(paths.some((path) => path.includes('/turns'))).toBe(false)
})

it('clears an earlier removal message when the original is deliberately linked again', async () => {
  const user = userEvent.setup()
  let linked = true
  let version = 5
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url === '/api/photos/detach') {
        linked = false
        version++
        return new Response(JSON.stringify({ ...photo, updated_at: version }))
      }
      if (url === '/api/photos/attach') {
        linked = true
        version++
        return new Response(JSON.stringify({ ...photo, updated_at: version }))
      }
      if (url.startsWith('/api/photos?limit=5'))
        return new Response(
          JSON.stringify({
            items: [{ ...photo, updated_at: version }],
            next_cursor: null,
          }),
        )
      if (url.startsWith('/api/photos?asset_id=target'))
        return new Response(
          JSON.stringify({
            items: linked ? [{ ...photo, updated_at: version }] : [],
            next_cursor: null,
          }),
        )
      return new Response(
        JSON.stringify({ items: [], allow_external_ai: false }),
      )
    }),
  )
  render(<PhotosPanel assetId="target" csrfToken="csrf" />)
  await user.click(await screen.findByRole('button', { name: /receipt.jpg/ }))
  await user.click(
    screen.getByRole('button', { name: 'Remove photo from this item' }),
  )
  await screen.findByText(/Photo removed from this item/)
  await user.click(screen.getByText('Use a photo already saved'))
  await user.click(screen.getByRole('button', { name: 'Load saved photos' }))
  await user.click(await screen.findByRole('button', { name: /receipt.jpg/ }))
  await user.click(
    screen.getByRole('button', { name: 'Link selected photo to this item' }),
  )
  await screen.findByText(/Photo linked to this item/)
  expect(
    screen.queryByText(/Photo removed from this item/),
  ).not.toBeInTheDocument()
})
