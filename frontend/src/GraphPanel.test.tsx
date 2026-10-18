import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { GraphPanel } from './GraphPanel'

const car = { id: 'car', name: 'Car', kind: 'asset', source_id: 'source' }
const garage = {
  id: 'garage',
  name: 'Garage',
  kind: 'place',
  source_id: 'source',
}
const edge = {
  id: 'edge',
  subject_id: 'car',
  object_id: 'garage',
  predicate: 'stored_in',
  value: null,
  status: 'inferred',
  evidence: [{ source_id: 'source', quote: 'Car is in Garage' }],
  valid_from: null,
  valid_to: null,
  recorded_at: 100,
}
afterEach(() => vi.unstubAllGlobals())

it('shows only stored relationships, opens their evidence and follows a node', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string) => ({
      ok: true,
      json: async () =>
        path === '/api/graph/entities'
          ? { items: [car, garage], next_cursor: null }
          : path.startsWith('/api/chat/sources/')
            ? { id: 'source', text: 'Car is in Garage', next_offset: null }
            : {
                entity: path.includes('garage') ? garage : car,
                nodes: [car, garage],
                edges: [edge],
                facts: [],
                truncated: false,
                next_fact_cursor: null,
              },
    })),
  )
  const openAsset = vi.fn()
  render(<GraphPanel csrfToken="csrf" onOpenAsset={openAsset} />)
  await userEvent.click(
    await screen.findByRole('button', {
      name: 'Inspect connection: stored_in (inferred)',
    }),
  )
  expect(screen.getByText('inferred', { exact: true })).toBeVisible()
  await userEvent.click(
    screen.getByRole('button', { name: 'Open asset details and photos' }),
  )
  expect(openAsset).toHaveBeenCalledWith('car')
  await userEvent.click(screen.getByRole('button', { name: 'Open evidence 1' }))
  expect(
    await screen.findByText('Car is in Garage', { selector: '.chat-text' }),
  ).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: /^Focus Garage$/ }))
  expect(await screen.findByRole('heading', { name: /^Garage$/ })).toBeVisible()
})

it('shows an honest empty graph without invented example nodes', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], next_cursor: null }),
    }),
  )
  render(<GraphPanel csrfToken="csrf" />)
  expect(await screen.findByText(/No graph records yet/)).toBeVisible()
  expect(
    screen.queryByRole('group', { name: 'Knowledge graph' }),
  ).not.toBeInTheDocument()
})
