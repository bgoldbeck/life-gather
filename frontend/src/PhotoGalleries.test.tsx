import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { PhotosPanel } from './PhotosPanel'

afterEach(() => vi.unstubAllGlobals())

const photo = (id: string) => ({
  id,
  filename: `${id}.jpg`,
  purpose: 'photo',
  size: 1000,
  width: 200,
  height: 100,
  updated_at: 5,
  source_id: null,
  deleted_at: null,
})

function server() {
  const photos = [photo('red'), photo('blue')]
  const galleries: Record<string, unknown>[] = []
  const members: Record<string, string[]> = {}
  const calls: { url: string; init?: RequestInit }[] = []
  const view = (gallery: Record<string, unknown>) => ({
    ...gallery,
    photo_count: members[gallery.id as string].length,
    cover_photo_id: members[gallery.id as string][0] ?? null,
  })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      const body = init?.body ? JSON.parse(init.body as string) : {}
      let result: unknown = { items: [], next_cursor: null }
      const match = url.match(/^\/api\/photo-galleries\/([^/]+)(\/.*)?$/)
      if (url === '/api/photo-galleries' && init?.method === 'POST') {
        const gallery = { id: 'trip', updated_at: 1, ...body }
        galleries.push(gallery)
        members.trip = []
        result = view(gallery)
      } else if (url === '/api/photo-galleries')
        result = { items: galleries.map(view) }
      else if (match?.[2] === '/photos') {
        members[match[1]].push(...body.photo_ids)
        result = { ...view(galleries[0]), added_count: body.photo_ids.length }
      } else if (match?.[2] === '/photos/remove') {
        members[match[1]] = members[match[1]].filter(
          (id) => id !== body.photo_id,
        )
        result = view(galleries[0])
      } else if (match?.[2] === '/delete') {
        galleries.splice(0)
        result = { id: match[1], deleted: true }
      } else if (url.startsWith('/api/photos?')) {
        const gallery = new URL(url, 'http://x').searchParams.get('gallery_id')
        result = {
          items: gallery
            ? photos.filter((row) => members[gallery]?.includes(row.id))
            : photos,
          next_cursor: null,
        }
      } else if (url.endsWith('/galleries'))
        result = {
          items: galleries
            .filter((g) => members[g.id as string].includes(url.split('/')[3]))
            .map(view),
        }
      else if (url.startsWith('/api/photos/')) result = photo(url.split('/')[3])
      else if (url === '/api/settings') result = { allow_external_ai: false }
      return new Response(JSON.stringify(result))
    }),
  )
  return { calls }
}

it('creates a gallery, adds several photos and removes one from details', async () => {
  const user = userEvent.setup()
  const { calls } = server()
  render(<PhotosPanel csrfToken="csrf" />)
  const bar = await screen.findByRole('region', { name: 'Galleries' })
  await user.click(within(bar).getByRole('button', { name: 'New gallery' }))
  await user.type(screen.getByLabelText('Gallery name'), 'Moving day')
  await user.type(screen.getByLabelText('Event date (optional)'), '2026-05-02')
  await user.click(screen.getByRole('button', { name: 'Create gallery' }))
  const header = await screen.findByRole('region', {
    name: 'Gallery Moving day',
  })
  expect(within(header).getByText(/ · 0 photos$/)).toBeTruthy()
  expect(
    await screen.findByText(
      'No photos in this gallery yet. Use Add photos to choose saved ones.',
    ),
  ).toBeTruthy()
  const create = calls.find(
    (call) =>
      call.url === '/api/photo-galleries' && call.init?.method === 'POST',
  )!
  expect(JSON.parse(create.init!.body as string)).toEqual({
    title: 'Moving day',
    event_on: '2026-05-02',
  })
  expect(create.init?.headers).toMatchObject({ 'X-CSRF-Token': 'csrf' })

  await user.click(within(header).getByRole('button', { name: 'Add photos' }))
  await user.click(
    await within(header).findByRole('checkbox', { name: 'red.jpg' }),
  )
  await user.click(within(header).getByRole('checkbox', { name: 'blue.jpg' }))
  await user.click(
    within(header).getByRole('button', { name: 'Add 2 photos to gallery' }),
  )
  await screen.findByText(
    '2 photos added to Moving day. No AI request was made.',
  )
  expect(within(header).getByText(/ · 2 photos$/)).toBeTruthy()
  const grid = screen
    .getAllByRole('list')
    .find((list) => list.classList.contains('photo-grid'))!
  await waitFor(() =>
    expect(within(grid).getAllByRole('listitem')).toHaveLength(2),
  )

  await user.click(within(grid).getByRole('button', { name: /red\.jpg/ }))
  const details = screen.getByRole('region', { name: 'Photo details' })
  await user.click(
    await within(details).findByRole('button', {
      name: 'Remove from Moving day',
    }),
  )
  await within(details).findByText('Not in a gallery yet.')
  await waitFor(() =>
    expect(within(grid).getAllByRole('listitem')).toHaveLength(1),
  )
  expect(
    calls.some(
      (call) =>
        call.url === '/api/photo-galleries/trip/photos/remove' &&
        call.init?.body === JSON.stringify({ photo_id: 'red' }),
    ),
  ).toBe(true)
})

it('deletes a gallery but keeps its photos', async () => {
  const user = userEvent.setup()
  const { calls } = server()
  render(<PhotosPanel csrfToken="csrf" />)
  const bar = await screen.findByRole('region', { name: 'Galleries' })
  await user.click(within(bar).getByRole('button', { name: 'New gallery' }))
  await user.type(screen.getByLabelText('Gallery name'), 'Attic')
  await user.click(screen.getByRole('button', { name: 'Create gallery' }))
  const header = await screen.findByRole('region', { name: 'Gallery Attic' })
  await user.click(within(header).getByText('Delete gallery'))
  await user.click(
    within(header).getByRole('button', { name: 'Delete gallery, keep photos' }),
  )
  await screen.findByText('Gallery deleted. Its photos remain saved.')
  expect(
    within(bar)
      .getByRole('button', { name: 'All photos' })
      .getAttribute('aria-pressed'),
  ).toBe('true')
  expect(calls.at(-1)?.url).toMatch(/^\/api\/photos\?/)
  expect(await screen.findAllByRole('button', { name: /\.jpg/ })).toHaveLength(
    2,
  )
})

it('shows no gallery controls inside an item photo panel', async () => {
  const { calls } = server()
  render(<PhotosPanel csrfToken="csrf" assetId="asset" />)
  await screen.findAllByRole('button', { name: /\.jpg/ })
  expect(screen.queryByRole('region', { name: 'Galleries' })).toBeNull()
  expect(
    calls.some((call) => call.url.startsWith('/api/photo-galleries')),
  ).toBe(false)
})
