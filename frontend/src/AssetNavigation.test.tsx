import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { AssetsPanel } from './AssetsPanel'

afterEach(() => vi.unstubAllGlobals())
const assets = ['a', 'b'].map((id) => ({
  id,
  name: `Synthetic ${id}`,
  source_id: `source-${id}`,
  recorded_at: 100,
}))
function detail(id: string) {
  return {
    asset: assets.find((item) => item.id === id),
    in_inventory: true,
    decisions: [],
    facts: [],
    actions: [],
    action_head: '',
    next_action_cursor: null,
    next_fact_cursor: null,
    next_decision_cursor: null,
  }
}
const response = (value: unknown) => new Response(JSON.stringify(value))
function deferred() {
  let finish!: (value: Response) => void
  const promise = new Promise<Response>((resolve) => {
    finish = resolve
  })
  return { promise, finish }
}

it('clears loading when a reload supersedes an older correction-history page', async () => {
  const user = userEvent.setup()
  const older = deferred()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.startsWith('/api/assets?'))
        return response({ items: assets, next_cursor: null })
      if (url === '/api/assets/a')
        return response({
          ...detail('a'),
          next_action_cursor: 'old',
          actions: [
            {
              id: 'new',
              operation: 'ownership',
              recorded_at: 100,
              note: 'Current correction',
              source_id: 'source-a',
            },
          ],
        })
      if (url.includes('action_cursor=old')) return older.promise
      return response({ items: [], next_cursor: null })
    }),
  )
  render(<AssetsPanel initialAssetId="a" />)
  await screen.findByRole('heading', { name: 'Synthetic a' })
  await user.click(screen.getByText('Make a correction'))
  await user.click(screen.getByRole('button', { name: 'More corrections' }))
  await user.click(screen.getByRole('button', { name: 'Reload item' }))
  await act(async () => older.finish(response({ ...detail('a'), actions: [] })))
  expect(screen.queryByText('Loading records…')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Synthetic b' })).toBeEnabled()
})

it('ignores a stale asset-list page after a new graph selection starts a fresh view', async () => {
  const user = userEvent.setup()
  const older = deferred()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.startsWith('/api/assets?') && url.includes('cursor=next'))
        return older.promise
      if (url.startsWith('/api/assets?'))
        return response({ items: assets, next_cursor: 'next' })
      if (url === '/api/assets/a') return response(detail('a'))
      if (url === '/api/assets/b') return response(detail('b'))
      return response({ items: [], next_cursor: null })
    }),
  )
  const view = render(<AssetsPanel initialAssetId="a" />)
  await screen.findByRole('heading', { name: 'Synthetic a' })
  await user.click(screen.getByRole('button', { name: 'More assets' }))
  view.rerender(<AssetsPanel initialAssetId="b" />)
  await screen.findByRole('heading', { name: 'Synthetic b' })
  await act(async () =>
    older.finish(
      response({
        items: [
          {
            id: 'stale',
            name: 'STALE ASSET',
            source_id: 'old',
            recorded_at: 100,
          },
        ],
        next_cursor: null,
      }),
    ),
  )
  expect(
    screen.queryByRole('button', { name: 'STALE ASSET' }),
  ).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Synthetic b' })).toBeVisible()
})

it('ignores a late reload after the user selects another asset', async () => {
  const user = userEvent.setup()
  const reload = deferred()
  let aReads = 0
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.startsWith('/api/assets?'))
        return response({ items: assets, next_cursor: null })
      if (url === '/api/assets/a')
        return ++aReads === 1 ? response(detail('a')) : reload.promise
      if (url === '/api/assets/b') return response(detail('b'))
      return response({ items: [], next_cursor: null })
    }),
  )
  render(<AssetsPanel />)
  await user.click(await screen.findByRole('button', { name: 'Synthetic a' }))
  await user.click(screen.getByText('Make a correction'))
  await user.click(screen.getByRole('button', { name: 'Reload item' }))
  await user.click(screen.getByRole('button', { name: 'Synthetic b' }))
  await screen.findByRole('heading', { name: 'Synthetic b' })
  await act(async () => reload.finish(response(detail('a'))))
  expect(screen.getByRole('heading', { name: 'Synthetic b' })).toBeVisible()
  expect(
    screen.queryByRole('heading', { name: 'Synthetic a' }),
  ).not.toBeInTheDocument()
})

it('does not reload the previous item when its saved correction returns after navigation', async () => {
  const user = userEvent.setup()
  const write = deferred()
  let aReads = 0
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.startsWith('/api/assets?'))
        return response({ items: assets, next_cursor: null })
      if (url === '/api/assets/a') {
        aReads++
        return response(detail('a'))
      }
      if (url === '/api/assets/b') return response(detail('b'))
      if (url === '/api/assets/actions') return write.promise
      return response({ items: [], next_cursor: null })
    }),
  )
  render(<AssetsPanel csrfToken="csrf" />)
  await user.click(await screen.findByRole('button', { name: 'Synthetic a' }))
  await user.click(screen.getByText('Make a correction'))
  await user.selectOptions(screen.getByLabelText('Ownership statement'), 'sold')
  await user.type(
    screen.getByLabelText('Why are you changing it?'),
    'Synthetic sale.',
  )
  await user.click(screen.getByRole('button', { name: 'Save correction' }))
  await user.click(screen.getByRole('button', { name: 'Synthetic b' }))
  await screen.findByRole('heading', { name: 'Synthetic b' })
  await act(async () => write.finish(response({ id: 'saved' })))
  expect(screen.getByRole('heading', { name: 'Synthetic b' })).toBeVisible()
  expect(aReads).toBe(1)
})

it('does not append a previous asset correction page after graph navigation changes the selection', async () => {
  const user = userEvent.setup()
  const older = deferred()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.startsWith('/api/assets?'))
        return response({ items: assets, next_cursor: null })
      if (url === '/api/assets/a')
        return response({
          ...detail('a'),
          next_action_cursor: 'old',
          actions: [
            {
              id: 'new',
              operation: 'ownership',
              recorded_at: 100,
              note: 'Current a correction',
              source_id: 'source-a',
            },
          ],
        })
      if (url === '/api/assets/b') return response(detail('b'))
      if (url.includes('action_cursor=old')) return older.promise
      return response({ items: [], next_cursor: null })
    }),
  )
  const view = render(<AssetsPanel initialAssetId="a" />)
  await user.click(
    await screen.findByRole('button', { name: 'More corrections' }),
  )
  view.rerender(<AssetsPanel initialAssetId="b" />)
  await screen.findByRole('heading', { name: 'Synthetic b' })
  await act(async () =>
    older.finish(
      response({
        ...detail('a'),
        actions: [
          {
            id: 'old',
            operation: 'ownership',
            recorded_at: 50,
            note: 'STALE CORRECTION',
            source_id: 'source-a',
          },
        ],
      }),
    ),
  )
  expect(screen.queryByText('STALE CORRECTION')).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Synthetic b' })).toBeVisible()
})
