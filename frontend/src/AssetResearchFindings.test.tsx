import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { AssetResearchFindings } from './AssetResearchFindings'

afterEach(() => vi.unstubAllGlobals())
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status })
const finding = {
  id: 'finding-1',
  question: 'DW-100 manual',
  researched_at: '2026-10-22T08:30:15Z',
  url: 'https://manuals.example.com/dw-100.pdf',
  title: 'DW-100 Owner’s Manual',
  published: 'March 3, 2024',
  excerpt_kind: 'source',
  excerpts: ['Clean the filter once a month.'],
  recorded_at: 1_761_000_000_000_000,
  identity_note: 'Web results describe a product model, not your own item.',
}

function harness(initial: (typeof finding)[]) {
  let items = initial
  const removals: unknown[] = []
  const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
    if (path === '/api/research-findings/assets/asset-1') return json({ items })
    if (path === '/api/research-findings/remove') {
      removals.push(JSON.parse(String(init?.body)))
      items = []
      return json({ ...finding, removed_at: 1 })
    }
    throw new Error('Unexpected synthetic request: ' + path)
  })
  vi.stubGlobal('fetch', fetcher)
  return {
    removals,
    fetcher,
    add: () => {
      items = [finding]
    },
  }
}

it('shows saved findings with source, dates and excerpts, and removes after confirming', async () => {
  const { removals } = harness([finding])
  render(<AssetResearchFindings assetId="asset-1" csrfToken="csrf" />)
  const link = await screen.findByRole('link', {
    name: 'DW-100 Owner’s Manual',
  })
  expect(link).toHaveAttribute('href', 'https://manuals.example.com/dw-100.pdf')
  expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  expect(screen.getByText(/Page dated March 3, 2024/)).toBeVisible()
  expect(screen.getByText('Looked up: DW-100 manual')).toBeVisible()
  expect(screen.getByText('Clean the filter once a month.')).toBeVisible()
  expect(screen.getByText(/do not establish ownership/)).toBeVisible()
  const user = userEvent.setup()
  await user.click(
    screen.getByRole('button', { name: 'Remove DW-100 Owner’s Manual' }),
  )
  expect(removals).toEqual([])
  await user.click(screen.getByRole('button', { name: 'Confirm remove' }))
  expect(await screen.findByText(/No research saved yet/)).toBeVisible()
  expect(removals).toEqual([{ finding_id: 'finding-1' }])
})

it('reloads when a finding is saved to this asset from Chat', async () => {
  const { add, fetcher } = harness([])
  render(<AssetResearchFindings assetId="asset-1" csrfToken="csrf" />)
  expect(await screen.findByText(/No research saved yet/)).toBeVisible()
  add()
  act(() => {
    window.dispatchEvent(
      new CustomEvent('lifegather:research-finding-saved', {
        detail: { assetId: 'other' },
      }),
    )
  })
  expect(fetcher).toHaveBeenCalledTimes(1)
  act(() => {
    window.dispatchEvent(
      new CustomEvent('lifegather:research-finding-saved', {
        detail: { assetId: 'asset-1' },
      }),
    )
  })
  expect(
    await screen.findByRole('link', { name: 'DW-100 Owner’s Manual' }),
  ).toBeVisible()
})
