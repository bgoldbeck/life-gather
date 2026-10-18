import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { CandidateComparison } from './CandidateComparison'
afterEach(() => vi.unstubAllGlobals())
const candidates = [
  { id: 'asset-a', name: 'Same model' },
  { id: 'asset-b', name: 'Same model' },
  { id: 'asset-c', name: 'Other item' },
]
function detail(id: string, serial: string) {
  return {
    asset: { id, name: 'Synthetic ' + id, source_id: 'original-' + id },
    in_inventory: id !== 'asset-b',
    decisions: [
      {
        id: 'decision-' + id,
        manufacturer: 'Acme',
        model: 'M1',
        serial,
        quote: 'Synthetic evidence <script>untrusted()</script>',
        source_id: 'evidence-' + id,
        superseded_at: null,
      },
    ],
    actions: [
      {
        id: 'action-' + id,
        note: 'I sold this item.',
        source_id: 'correction-' + id,
        recorded_at: 1792348800000000,
        direction: 'incoming',
        asset_name: 'Original item',
      },
    ],
    next_action_cursor: 'more',
  }
}
it('loads only explicitly inspected bounded snapshots and opens exact evidence without selecting identities', async () => {
  const user = userEvent.setup()
  const onOpen = vi.fn()
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return new Response(
        JSON.stringify(
          detail(
            url.includes('asset-a') ? 'asset-a' : 'asset-b',
            url.includes('asset-a') ? 'S1' : 'S2',
          ),
        ),
      )
    }),
  )
  render(<CandidateComparison candidates={candidates} onOpen={onOpen} />)
  expect(calls).toHaveLength(0)
  await user.click(
    screen.getByRole('button', { name: 'Inspect Same model (asset-a)' }),
  )
  await user.click(
    screen.getByRole('button', { name: 'Inspect Same model (asset-b)' }),
  )
  expect(await screen.findByText('S1')).toBeVisible()
  expect(await screen.findByText('S2')).toBeVisible()
  const first = screen.getByRole('article', {
    name: 'Candidate Same model (asset-a)',
  })
  await user.click(
    within(first).getByRole('button', { name: 'Open identity evidence' }),
  )
  expect(onOpen).toHaveBeenCalledWith('evidence-asset-a')
  expect(
    within(first).getByText('Evidence received from Original item.'),
  ).toBeVisible()
  expect(screen.getByText(/Outside current inventory/)).toBeVisible()
  expect(
    within(first).getByText('Synthetic evidence <script>untrusted()</script>'),
  ).toBeVisible()
  expect(
    calls.every((call) => call.url.endsWith('?limit=3') && !call.init?.method),
  ).toBe(true)
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
})
it('keeps at most two snapshots and ignores a closed slow response', async () => {
  const user = userEvent.setup()
  let finish: ((response: Response) => void) | undefined
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      url.includes('asset-a')
        ? await new Promise<Response>((resolve) => {
            finish = resolve
          })
        : new Response(
            JSON.stringify(
              detail(url.includes('asset-b') ? 'asset-b' : 'asset-c', 'S2'),
            ),
          ),
    ),
  )
  render(<CandidateComparison candidates={candidates} onOpen={vi.fn()} />)
  await user.click(
    screen.getByRole('button', { name: 'Inspect Same model (asset-a)' }),
  )
  await user.click(
    screen.getByRole('button', { name: 'Inspect Same model (asset-b)' }),
  )
  await user.click(
    screen.getByRole('button', { name: 'Inspect Other item (asset-c)' }),
  )
  await act(async () =>
    finish!(new Response(JSON.stringify(detail('asset-a', 'SLOW')))),
  )
  expect(screen.getAllByRole('article')).toHaveLength(2)
  expect(screen.queryByText('SLOW')).not.toBeInTheDocument()
  expect(
    screen.queryByRole('article', { name: 'Candidate Same model (asset-a)' }),
  ).not.toBeInTheDocument()
})
it('pages candidate buttons and retries a failed private read', async () => {
  const user = userEvent.setup()
  let failure = true
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      failure
        ? new Response('', { status: 400 })
        : new Response(JSON.stringify(detail('asset-5', 'S5'))),
    ),
  )
  const many = Array.from({ length: 7 }, (_, i) => ({
    id: 'asset-' + i,
    name: 'Candidate ' + i,
  }))
  render(<CandidateComparison candidates={many} onOpen={vi.fn()} />)
  expect(
    screen.queryByRole('button', { name: 'Inspect Candidate 5 (asset-5)' }),
  ).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Next candidates' }))
  await user.click(
    screen.getByRole('button', { name: 'Inspect Candidate 5 (asset-5)' }),
  )
  await screen.findByRole('alert')
  failure = false
  await user.click(screen.getByRole('button', { name: 'Retry inspection' }))
  await screen.findByText('S5')
  expect(screen.getByRole('button', { name: 'Next candidates' })).toBeDisabled()
})
