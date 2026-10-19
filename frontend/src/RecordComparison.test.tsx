import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { RecordComparison } from './RecordComparison'

afterEach(() => vi.unstubAllGlobals())
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status })
function deferred() {
  let release!: (value: Response) => void
  const promise = new Promise<Response>((resolve) => {
    release = resolve
  })
  return { promise, release }
}
const complete = {
  complete: true,
  records: [
    {
      id: 'old',
      name: 'Original drill',
      source_id: 'source-old',
      in_inventory: true,
    },
    {
      id: 'target',
      name: 'Other drill',
      source_id: 'source-target',
      in_inventory: false,
    },
  ],
  references: [],
  counts: { statements: 1, aliases: 0, photos: 0, receipt_lines: 1 },
  limited_sections: [],
  source_states: {
    'source-old': { is_current: false, current_source_id: 'source-current' },
  },
  warnings: [
    {
      code: 'statements_differ',
      predicate: 'color',
      message: 'Preserve both conflicting source statements.',
    },
  ],
  sections: {
    statements: [
      {
        id: 'fact',
        subject_id: 'old',
        predicate: 'color',
        object_id: null,
        value: 'red',
        status: 'stated',
        recorded_at: 1000000,
        valid_from: null,
        valid_to: null,
        evidence: [
          { source_id: 'source-old', quote: 'Synthetic source says red.' },
        ],
      },
    ],
    aliases: [],
    photos: [],
    associations: [],
    receipt_lines: [
      {
        key: 'line',
        asset_id: 'old',
        source_id: 'receipt',
        name: 'Drill',
        quantity: 2,
        unit: 1,
        source_current: true,
        claim: { line_total: '49.90', currency: 'USD', purchase_date: null },
      },
    ],
    purchase_evidence: [
      {
        id: 'order',
        purchase_id: 'purchase',
        source_id: 'order-source',
        source_current: true,
        role: 'order',
        amount_minor: 4990,
        currency: 'JPY',
        quote: 'Synthetic order.',
        occurred_on: null,
      },
    ],
  },
}
function server(response: () => Promise<Response>) {
  const fetcher = vi.fn(async (path: string) =>
    path.startsWith('/api/assets?')
      ? json({
          items: [
            { id: 'old', name: 'Original drill' },
            { id: 'target', name: 'Other drill' },
          ],
          next_cursor: null,
        })
      : response(),
  )
  vi.stubGlobal('fetch', fetcher)
  return fetcher
}
async function choose() {
  const user = userEvent.setup()
  await user.click(
    screen.getByRole('button', { name: 'Find comparison items' }),
  )
  await user.selectOptions(
    await screen.findByLabelText('Compare with'),
    'target',
  )
  await user.click(
    screen.getByRole('button', { name: 'Compare selected records' }),
  )
  return user
}

it('requires a deliberate selection and shows sources, exact money and conflict scope', async () => {
  const fetcher = server(async () => json(complete))
  const onOpen = vi.fn(async () => {})
  render(
    <RecordComparison
      assetId="old"
      assetName="Original drill"
      csrfToken="csrf"
      onOpen={onOpen}
    />,
  )
  expect(fetcher).not.toHaveBeenCalled()
  expect(
    screen.getByRole('button', { name: 'Compare selected records' }),
  ).toBeDisabled()
  const user = await choose()
  expect(await screen.findByText(/Complete within/)).toBeVisible()
  expect(screen.getByText(/Whole line: USD 49.90/)).toBeVisible()
  expect(screen.getByText(/order · purchase purchase · JPY 4990/)).toBeVisible()
  expect(
    screen.getByText('Preserve both conflicting source statements.'),
  ).toBeVisible()
  expect(screen.getByText('Synthetic source says red.')).toBeVisible()
  expect(
    screen.queryByRole('button', { name: /^merge/i }),
  ).not.toBeInTheDocument()
  const call = fetcher.mock.calls.find(
    ([path]) => path === '/api/assets/comparison',
  )
  expect(
    JSON.parse(String((call as unknown as [string, RequestInit])[1]?.body)),
  ).toEqual({ asset_id: 'old', target_asset_id: 'target' })
  await user.click(
    screen.getByRole('button', { name: 'View statement evidence' }),
  )
  expect(onOpen).toHaveBeenLastCalledWith('source-old')
  await user.click(
    screen.getAllByRole('button', { name: 'View current source' })[0],
  )
  expect(onOpen).toHaveBeenLastCalledWith('source-current')
})

it('shows explicit limits without partial record details', async () => {
  server(async () =>
    json({
      ...complete,
      complete: false,
      sections: {},
      warnings: [],
      counts: { statements: 51 },
      limited_sections: ['statements'],
    }),
  )
  render(
    <RecordComparison
      assetId="old"
      assetName="Original drill"
      csrfToken="csrf"
      onOpen={async () => {}}
    />,
  )
  await choose()
  expect(
    await screen.findByText(/A complete comparison is unavailable/),
  ).toBeVisible()
  expect(screen.getByText('At least 51')).toBeVisible()
  expect(
    screen.queryByText('Synthetic source says red.'),
  ).not.toBeInTheDocument()
  expect(
    screen.queryByRole('article', { name: 'Current record Original drill' }),
  ).not.toBeInTheDocument()
})

it('uses the exact literal display when a JSON integer exceeds browser precision', async () => {
  server(async () =>
    json({
      ...complete,
      sections: {
        ...complete.sections,
        statements: [
          {
            ...complete.sections.statements[0],
            value: 9007199254740992,
            display_value: '9007199254740993',
          },
        ],
      },
    }),
  )
  render(
    <RecordComparison
      assetId="old"
      assetName="Original drill"
      csrfToken="csrf"
      onOpen={async () => {}}
    />,
  )
  await choose()
  expect(await screen.findByText(/9007199254740993/)).toBeVisible()
  expect(screen.queryByText(/9007199254740992/)).not.toBeInTheDocument()
})

it.each([200, 500])(
  'ignores a delayed comparison (%s) after clearing it',
  async (status) => {
    const late = deferred()
    server(() => late.promise)
    render(
      <RecordComparison
        assetId="old"
        assetName="Original drill"
        csrfToken="csrf"
        onOpen={async () => {}}
      />,
    )
    const user = await choose()
    await user.click(screen.getByRole('button', { name: 'Clear comparison' }))
    await act(async () => late.release(json(complete, status)))
    expect(screen.queryByText(/Complete within/)).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText(/Loading current/)).not.toBeInTheDocument()
  },
)

it('keeps a newer comparison loading when an older request finishes', async () => {
  const old = deferred(),
    current = deferred()
  let calls = 0
  server(() => (++calls === 1 ? old.promise : current.promise))
  render(
    <RecordComparison
      assetId="old"
      assetName="Original drill"
      csrfToken="csrf"
      onOpen={async () => {}}
    />,
  )
  const user = await choose()
  await user.click(screen.getByRole('button', { name: 'Clear comparison' }))
  await user.click(
    screen.getByRole('button', { name: 'Compare selected records' }),
  )
  await act(async () => old.release(json(complete)))
  expect(screen.getByText(/Loading current/)).toBeVisible()
  expect(screen.queryByText(/Complete within/)).not.toBeInTheDocument()
  await act(async () => current.release(json(complete)))
  expect(await screen.findByText(/Complete within/)).toBeVisible()
})

it('clears prior results on item change and recovers from read errors', async () => {
  let failed = true
  server(async () => json(complete, failed ? 503 : 200))
  const view = render(
    <RecordComparison
      key="old"
      assetId="old"
      assetName="Original drill"
      csrfToken="csrf"
      onOpen={async () => {}}
    />,
  )
  const user = await choose()
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Unable to compare',
  )
  failed = false
  await user.click(
    screen.getByRole('button', { name: 'Compare selected records' }),
  )
  expect(await screen.findByText(/Complete within/)).toBeVisible()
  view.rerender(
    <RecordComparison
      key="other"
      assetId="other"
      assetName="Saw"
      csrfToken="csrf"
      onOpen={async () => {}}
    />,
  )
  expect(screen.queryByText(/Complete within/)).not.toBeInTheDocument()
  expect(
    screen.getByRole('button', { name: 'Compare selected records' }),
  ).toBeDisabled()
})
