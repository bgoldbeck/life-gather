import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { Workspace } from './App'
import { GlobalSearch, type SearchResult } from './GlobalSearch'

afterEach(() => vi.unstubAllGlobals())
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status })

const results: SearchResult[] = [
  { kind: 'asset', id: 'a1', title: 'Blue kayak', detail: 'asset' },
  { kind: 'record', id: 'r1', title: 'Kayak club', detail: 'organization' },
  { kind: 'photo', id: 'p1', title: 'kayak plate.jpg', detail: 'photo' },
  {
    kind: 'document',
    id: 'd1',
    title: 'kayak manual.pdf',
    detail: '…kayak care…',
  },
  {
    kind: 'source',
    id: 's1',
    title: 'Bought a kayak',
    detail: 'Bought a kayak',
    photo_id: null,
    document_id: null,
  },
  {
    kind: 'source',
    id: 's2',
    title: 'Kayak plate transcription',
    detail: 'Kayak plate transcription',
    photo_id: 'p1',
    document_id: null,
  },
]

function server() {
  const fetch = vi.fn(async (url: string) => {
    if (url.startsWith('/api/search?q=')) {
      const query = decodeURIComponent(url.slice('/api/search?q='.length))
      return json({ query, items: query === 'kayak' ? results : [] })
    }
    if (url === '/api/photos/p1')
      return json({
        id: 'p1',
        filename: 'kayak plate.jpg',
        purpose: 'photo',
        size: 2048,
        width: 20,
        height: 10,
        updated_at: 5,
        source_id: null,
        deleted_at: null,
      })
    if (url === '/api/photos/p1/assets')
      return json({ items: [{ id: 'a1', name: 'Blue kayak' }] })
    if (url === '/api/documents/d1')
      return json({
        id: 'd1',
        filename: 'kayak manual.pdf',
        size: 10,
        pages: 1,
        extracted_text: 'kayak care',
        text_truncated: false,
        source_id: null,
        updated_at: 1,
        deleted_at: null,
      })
    if (/\/(a1|r1)\b/.test(url)) return json({ detail: 'not found' }, 404)
    if (url.startsWith('/api/chat/sources/s1'))
      return json({ id: 's1', text: 'Bought a kayak', next_offset: null })
    return json({ items: [], next_cursor: null })
  })
  vi.stubGlobal('fetch', fetch)
  return fetch
}

it('groups results, moves with arrow keys and opens the chosen result', async () => {
  const fetch = server()
  const onOpen = vi.fn()
  const user = userEvent.setup()
  render(<GlobalSearch onOpen={onOpen} />)
  const box = screen.getByRole('searchbox', {
    name: 'Search assets, photos, documents and sources',
  })
  await user.type(box, 'k')
  expect(fetch).not.toHaveBeenCalled()
  await user.type(box, 'ayak')
  const panel = await screen.findByRole('region', { name: 'Search results' })
  expect(await within(panel).findByText('6 matches')).toBeVisible()
  for (const group of [
    'Assets',
    'People, places and other records',
    'Photos',
    'Documents',
    'Sources',
  ])
    expect(within(panel).getByRole('region', { name: group })).toBeVisible()
  expect(within(panel).getByText('Opens its photo')).toBeVisible()
  expect(within(panel).getByText('Opens in Memories')).toBeVisible()
  // Only the settled query is sent, not one request per keystroke.
  expect(fetch).toHaveBeenCalledTimes(1)
  await user.keyboard('{ArrowDown}{ArrowDown}')
  expect(screen.getByRole('button', { name: /Kayak club/ })).toHaveFocus()
  await user.keyboard('{Enter}')
  expect(onOpen).toHaveBeenCalledWith(results[1])
  expect(
    screen.queryByRole('region', { name: 'Search results' }),
  ).not.toBeInTheDocument()

  await user.clear(box)
  await user.type(box, 'canoe')
  expect(await screen.findByText('No matches for “canoe”.')).toBeVisible()
  await user.keyboard('{Escape}')
  expect(
    screen.queryByRole('region', { name: 'Search results' }),
  ).not.toBeInTheDocument()
})

it('shows a readable error when search fails', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => json({ detail: 'nope' }, 500)),
  )
  const user = userEvent.setup()
  render(<GlobalSearch onOpen={vi.fn()} />)
  await user.type(screen.getByRole('searchbox'), 'kayak')
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Unable to search right now. Try again.',
  )
})

async function search(user: ReturnType<typeof userEvent.setup>) {
  const box = screen.getByRole('searchbox', {
    name: 'Search assets, photos, documents and sources',
  })
  await user.clear(box)
  await user.type(box, 'kayak')
  return screen.findByRole('region', { name: 'Search results' })
}

it('navigates from results to photos, assets, documents and sources', async () => {
  server()
  const user = userEvent.setup()
  render(<Workspace />)
  const main = () => screen.getByRole('main')

  let panel = await search(user)
  await user.click(
    await within(panel).findByRole('button', { name: /kayak plate\.jpg/ }),
  )
  expect(main()).toHaveAttribute('data-view', 'Photos')
  const detail = await screen.findByRole('region', { name: 'Photo details' })
  expect(within(detail).getByText('kayak plate.jpg')).toBeVisible()
  await user.click(
    await within(detail).findByRole('button', { name: 'Open Blue kayak' }),
  )
  expect(main()).toHaveAttribute('data-view', 'Assets')

  panel = await search(user)
  await user.click(
    await within(panel).findByRole('button', { name: /kayak manual\.pdf/ }),
  )
  expect(main()).toHaveAttribute('data-view', 'Documents')
  expect(
    await screen.findByRole('region', { name: 'Document review' }),
  ).toBeVisible()

  panel = await search(user)
  await user.click(
    await within(panel).findByRole('button', {
      name: /Kayak plate transcription/,
    }),
  )
  expect(main()).toHaveAttribute('data-view', 'Photos')
  expect(
    await screen.findByRole('region', { name: 'Photo details' }),
  ).toBeVisible()

  panel = await search(user)
  await user.click(
    await within(panel).findByRole('button', { name: /Bought a kayak/ }),
  )
  expect(main()).toHaveAttribute('data-view', 'Memories')
  const evidence = await screen.findByRole('region', {
    name: 'Original evidence',
  })
  expect(within(evidence).getByText(/Bought a kayak/)).toBeVisible()

  panel = await search(user)
  await user.click(
    await within(panel).findByRole('button', { name: /Kayak club/ }),
  )
  expect(main()).toHaveAttribute('data-view', 'Graph')

  // Plain navigation shows the page without the earlier selection.
  await user.click(screen.getByRole('button', { name: 'Photos' }))
  expect(
    screen.queryByRole('region', { name: 'Photo details' }),
  ).not.toBeInTheDocument()
})
