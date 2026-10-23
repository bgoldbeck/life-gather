import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ResearchResult, type WebResearch } from './ResearchResult'

afterEach(() => vi.unstubAllGlobals())
const research: WebResearch = {
  researched_at: '2026-10-22T09:00:00Z',
  queries: [],
  searches: 1,
  shared_record: null,
  identity_note: 'Synthetic product reference',
  sources: [
    {
      url: 'https://manual.example/item',
      title: 'Manual',
      published: null,
      excerpt_kind: 'source',
      excerpts: [],
    },
  ],
}

it('retains the request after an ambiguous server failure', async () => {
  const writes: Record<string, unknown>[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_path: string, init: RequestInit) => {
      writes.push(JSON.parse(String(init.body)))
      return new Response(
        JSON.stringify(
          writes.length === 1
            ? { detail: 'Upstream reply unavailable' }
            : { already_saved: true, removed_at: null },
        ),
        { status: writes.length === 1 ? 503 : 201 },
      )
    }),
  )
  render(
    <ResearchResult
      research={research}
      turnId="turn"
      csrfToken="csrf"
      target={{ id: 'asset', name: 'Synthetic item' }}
    />,
  )
  const user = userEvent.setup()
  await user.click(
    screen.getByRole('button', { name: 'Save to Synthetic item' }),
  )
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Upstream reply unavailable',
  )
  await user.click(
    screen.getByRole('button', { name: 'Save to Synthetic item' }),
  )
  expect(
    await screen.findByText('Already saved to Synthetic item'),
  ).toBeVisible()
  expect(writes[1]).toEqual(writes[0])
})

it('retries an uncertain save exactly, explains a removed receipt, and requires a new save intent', async () => {
  const writes: Record<string, unknown>[] = []
  const announced = vi.fn()
  window.addEventListener('lifegather:research-finding-saved', announced)
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_path: string, init: RequestInit) => {
      writes.push(JSON.parse(String(init.body)))
      if (writes.length === 1) throw new Error('Reply lost')
      return new Response(
        JSON.stringify({
          already_saved: writes.length === 2,
          removed_at: writes.length === 2 ? 123 : null,
        }),
        { status: 201 },
      )
    }),
  )
  render(
    <ResearchResult
      research={research}
      turnId="turn"
      csrfToken="csrf"
      target={{ id: 'asset', name: 'Synthetic item' }}
    />,
  )
  const user = userEvent.setup()
  await user.click(
    screen.getByRole('button', { name: 'Save to Synthetic item' }),
  )
  expect(await screen.findByRole('alert')).toHaveTextContent('Reply lost')
  await user.click(
    screen.getByRole('button', { name: 'Save to Synthetic item' }),
  )
  expect(
    await screen.findByText('Previously saved finding was removed.'),
  ).toBeVisible()
  expect(writes[1]).toEqual(writes[0])
  expect(announced).not.toHaveBeenCalled()
  await user.click(
    screen.getByRole('button', { name: 'Save again to Synthetic item' }),
  )
  expect(await screen.findByText('Saved to Synthetic item')).toBeVisible()
  expect(writes[2].request_id).not.toBe(writes[0].request_id)
  expect(announced).toHaveBeenCalledTimes(1)
  window.removeEventListener('lifegather:research-finding-saved', announced)
})
