import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ProfilesPanel } from './ProfilesPanel'

afterEach(() => vi.unstubAllGlobals())

it('creates an explicitly separate home record and opens its empty profile', async () => {
  const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.startsWith('/api/maintenance'))
      return new Response(JSON.stringify({ items: [], next_cursor: null }))
    const entity = {
      id: 'home',
      name: 'Synthetic home',
      kind: 'place',
      source_id: 'source',
    }
    return new Response(
      JSON.stringify(
        init?.method === 'POST'
          ? entity
          : path.startsWith('/api/graph/entities')
            ? { items: [], next_cursor: null }
            : { entity, facts: [], next_cursor: null },
      ),
    )
  })
  vi.stubGlobal('fetch', fetcher)
  render(<ProfilesPanel csrfToken="csrf" />)
  await userEvent.click(
    screen.getByText('Create a distinct home or vehicle record'),
  )
  await userEvent.type(screen.getByLabelText('Record name'), 'Synthetic home')
  await userEvent.type(
    screen.getByLabelText('Source statement'),
    'Synthetic test home statement',
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Create separate record' }),
  )
  expect(
    await screen.findByRole('heading', { name: 'Synthetic home' }),
  ).toBeVisible()
  expect(screen.getByText('No sourced profile details recorded.')).toBeVisible()
  const [, init] = fetcher.mock.calls.find(
    ([, input]) => input?.method === 'POST',
  )!
  expect(JSON.parse(String(init?.body))).toMatchObject({
    kind: 'home',
    name: 'Synthetic home',
    text: 'Synthetic test home statement',
  })
})

it('saves an exact sourced specification and exposes correction history', async () => {
  const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.startsWith('/api/maintenance'))
      return new Response(JSON.stringify({ items: [], next_cursor: null }))
    const entity = {
      id: 'car',
      name: 'Synthetic car',
      kind: 'asset',
      source_id: 'source',
    }
    if (path.startsWith('/api/graph/entities'))
      return new Response(
        JSON.stringify({ items: [entity], next_cursor: null }),
      )
    if (init?.method === 'POST')
      return new Response(JSON.stringify({ id: 'fact' }))
    return new Response(
      JSON.stringify({
        entity,
        facts: [
          {
            id: 'old',
            predicate: 'profile_model',
            value: 'Model A',
            status: 'stated',
            recorded_at: 100,
            superseded_at: null,
            valid_from: null,
            valid_to: null,
            evidence: [{ source_id: 'source' }],
          },
        ],
        next_cursor: null,
      }),
    )
  })
  vi.stubGlobal('fetch', fetcher)
  render(<ProfilesPanel csrfToken="csrf" />)
  await userEvent.click(
    await screen.findByRole('button', { name: 'Correct model' }),
  )
  await userEvent.clear(screen.getByLabelText('Exact value'))
  await userEvent.type(screen.getByLabelText('Exact value'), 'Model B')
  await userEvent.type(
    screen.getByLabelText('Original evidence or your statement'),
    'Correction: Model B',
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Save sourced detail' }),
  )
  expect(
    await screen.findByText('Detail saved with original evidence.'),
  ).toBeVisible()
  const call = fetcher.mock.calls.find(([, init]) => init?.method === 'POST')!
  expect(JSON.parse(String(call[1]?.body))).toMatchObject({
    entity_id: 'car',
    field: 'model',
    value: 'Model B',
    replaces_id: 'old',
    text: 'Correction: Model B',
  })
  await userEvent.click(screen.getByLabelText('Include correction history'))
  expect(fetcher.mock.calls.some(([url]) => url.includes('history=true'))).toBe(
    true,
  )
})
