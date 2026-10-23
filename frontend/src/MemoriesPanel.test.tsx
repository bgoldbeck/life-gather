import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { MemoriesPanel } from './MemoriesPanel'

afterEach(() => vi.unstubAllGlobals())
const item = {
  id: 'source',
  text: 'Original <script>filter</script>',
  kind: 'notes',
  recorded_at: 1000,
  is_current: true,
  is_correction: false,
}
const source = {
  ...item,
  next_offset: null,
  note: {
    root_source_id: 'source',
    current_source_id: 'source',
    is_current: true,
    can_correct: true,
  },
}

it('browses and searches source types and corrected history without AI calls', async () => {
  const user = userEvent.setup()
  const fetcher = vi.fn(
    async (url: string) =>
      new Response(
        JSON.stringify(
          url.includes('/sources/')
            ? source
            : { items: [item], next_cursor: null },
        ),
      ),
  )
  vi.stubGlobal('fetch', fetcher)
  render(<MemoriesPanel csrfToken="csrf" />)
  await user.click(
    await screen.findByRole('button', { name: /Open evidence:/ }),
  )
  expect(
    await screen.findByRole('heading', { name: 'Original evidence' }),
  ).toBeVisible()
  expect(document.querySelector('script')).toBeNull()
  await user.type(screen.getByLabelText('Search saved evidence'), 'filter')
  await user.click(screen.getByRole('button', { name: 'Search memories' }))
  await user.selectOptions(screen.getByLabelText('Source type'), 'photos')
  await user.click(screen.getByLabelText('Include earlier versions'))
  await waitFor(() =>
    expect(
      fetcher.mock.calls.some(([url]) =>
        url.includes('query=filter&kind=photos&include_history=true'),
      ),
    ).toBe(true),
  )
  expect(fetcher.mock.calls.every(([url]) => !url.includes('/turns'))).toBe(
    true,
  )
})

it('preserves capture request identity after a lost response and refreshes after correction', async () => {
  const user = userEvent.setup()
  const captures: RequestInit[] = []
  let corrected = false
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      let result: unknown = {
        items: [
          {
            ...item,
            id: corrected ? 'corrected' : 'source',
            text: corrected ? 'Corrected filter' : item.text,
          },
        ],
        next_cursor: null,
      }
      if (url === '/api/memories' && init?.method === 'POST') {
        captures.push(init)
        if (captures.length === 1) throw new TypeError('lost response')
        result = source
      } else if (url.endsWith('/corrections')) {
        corrected = true
        result = { source: { id: 'corrected' } }
      } else if (url.includes('/sources/'))
        result = corrected
          ? {
              ...source,
              id: 'corrected',
              text: 'Corrected filter',
              note: { ...source.note, current_source_id: 'corrected' },
            }
          : source
      return new Response(JSON.stringify(result))
    }),
  )
  render(<MemoriesPanel csrfToken="csrf" />)
  await screen.findByRole('button', { name: /Open evidence:/ })
  await user.click(screen.getByText('Save a memory'))
  await user.type(
    screen.getByLabelText('Your original words'),
    'Original exact words',
  )
  await user.click(screen.getByRole('button', { name: 'Save memory' }))
  expect(
    await screen.findByRole('button', { name: 'Retry same memory' }),
  ).toBeEnabled()
  expect(screen.getByLabelText('Your original words')).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Retry same memory' }))
  await screen.findByText(
    'Saved your exact words. No AI request or inventory change was made.',
  )
  expect(captures).toHaveLength(2)
  expect(captures[0].body).toBe(captures[1].body)
  expect(captures[0].headers).toMatchObject({ 'X-CSRF-Token': 'csrf' })
  await user.click(screen.getByRole('button', { name: 'Correct note' }))
  await user.clear(screen.getByLabelText('Corrected note'))
  await user.type(screen.getByLabelText('Corrected note'), 'Corrected filter')
  await user.click(screen.getByRole('button', { name: 'Save correction' }))
  await waitFor(() =>
    expect(
      screen.getByRole('button', { name: 'Open evidence: Corrected filter' }),
    ).toBeVisible(),
  )
})

it('ignores an old page that arrives after a new search', async () => {
  const user = userEvent.setup()
  let finishPage: (value: Response) => void = () => {}
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.includes('cursor=next'))
        return new Promise<Response>((resolve) => {
          finishPage = resolve
        })
      return new Response(
        JSON.stringify(
          url.includes('query=new')
            ? {
                items: [{ ...item, id: 'new', text: 'New result' }],
                next_cursor: null,
              }
            : { items: [item], next_cursor: 'next' },
        ),
      )
    }),
  )
  render(<MemoriesPanel csrfToken="csrf" />)
  await user.click(await screen.findByRole('button', { name: 'More memories' }))
  await user.type(screen.getByLabelText('Search saved evidence'), 'new')
  await user.click(screen.getByRole('button', { name: 'Search memories' }))
  await screen.findByRole('button', { name: 'Open evidence: New result' })
  finishPage(
    new Response(
      JSON.stringify({
        items: [{ ...item, id: 'old-page', text: 'Obsolete page' }],
        next_cursor: null,
      }),
    ),
  )
  await waitFor(() =>
    expect(screen.queryByText('Obsolete page')).not.toBeInTheDocument(),
  )
})

it('explains memories and deletes one only after confirmation', async () => {
  const user = userEvent.setup()
  let deleted = false
  const fetcher = vi.fn(async (url: string, _init?: RequestInit) => {
    if (url.includes('delete-many')) {
      deleted = true
      return new Response(JSON.stringify({ deleted_count: 1 }))
    }
    return new Response(
      JSON.stringify({ items: deleted ? [] : [item], next_cursor: null }),
    )
  })
  vi.stubGlobal('fetch', fetcher)
  render(<MemoriesPanel csrfToken="csrf" />)
  await user.click(screen.getByText('What are memories?'))
  expect(screen.getByText(/How the assistant uses them/)).toBeVisible()
  await user.click(
    await screen.findByRole('button', { name: /Delete memory:/ }),
  )
  await user.click(screen.getByRole('button', { name: 'Keep memory' }))
  expect(fetcher.mock.calls.some(([url]) => url.includes('delete'))).toBe(false)
  await user.click(screen.getByRole('button', { name: /Delete memory:/ }))
  await user.click(screen.getByRole('button', { name: 'Delete permanently' }))
  expect(await screen.findByText(/Memory deleted/)).toBeVisible()
  const call = fetcher.mock.calls.find(([url]) => url.includes('delete-many'))!
  const init = call[1]!
  expect(init.method).toBe('POST')
  expect(JSON.parse(String(init.body))).toEqual({
    memories: [{ source_id: 'source' }],
  })
  expect((init.headers as Record<string, string>)['X-CSRF-Token']).toBe('csrf')
  await waitFor(() =>
    expect(screen.queryByText(/Original <script>/)).toBeNull(),
  )
})

it('keeps the memory when deletion fails', async () => {
  const user = userEvent.setup()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      url.includes('delete-many')
        ? new Response('{}', { status: 500 })
        : new Response(JSON.stringify({ items: [item], next_cursor: null })),
    ),
  )
  render(<MemoriesPanel csrfToken="csrf" />)
  await user.click(
    await screen.findByRole('button', { name: /Delete memory:/ }),
  )
  await user.click(screen.getByRole('button', { name: 'Delete permanently' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Unable to confirm deletion. Refresh memories to check, or try again.',
  )
  expect(screen.getByText(/Original <script>/)).toBeVisible()
})

it('does not claim nothing changed when the deletion reply is lost', async () => {
  const user = userEvent.setup()
  let deleted = false
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.includes('delete-many')) {
        deleted = true
        throw new TypeError('Reply lost after commit')
      }
      return Response.json({ items: deleted ? [] : [item], next_cursor: null })
    }),
  )
  render(<MemoriesPanel csrfToken="csrf" />)
  await user.click(
    await screen.findByRole('button', { name: /Delete memory:/ }),
  )
  await user.click(screen.getByRole('button', { name: 'Delete permanently' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Unable to confirm deletion. Refresh memories to check, or try again.',
  )
  await user.click(screen.getByRole('button', { name: 'Refresh memories' }))
  await waitFor(() =>
    expect(screen.queryByText(/Original <script>/)).toBeNull(),
  )
  expect(screen.queryByRole('alert')).toBeNull()
})
