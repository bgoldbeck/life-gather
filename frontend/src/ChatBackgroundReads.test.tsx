import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ChatPanel } from './ChatPanel'

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
function server(
  override: (
    path: string,
    init?: RequestInit,
  ) => Promise<Response> | undefined = () => undefined,
) {
  const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
    const custom = override(path, init)
    if (custom) return custom
    if (path === '/api/chat/conversations')
      return json({
        items: [
          { id: 'main', title: 'Main conversation' },
          { id: 'other', title: 'Other conversation' },
        ],
        next_cursor: 'page-two',
      })
    if (path.includes('/turns') && init?.method === 'POST') {
      const body = JSON.parse(String(init.body))
      return json({
        id: 'saved',
        request_id: body.request_id,
        mode: 'save',
        text: body.text,
        state: 'complete',
        result: { text: 'Saved marker' },
      })
    }
    if (path.includes('/turns')) return json({ items: [], next_cursor: null })
    if (path === '/api/chat/usage') return json({ requests: 0 })
    if (path === '/api/chat/preferences')
      return json({ credential_id: '', model: '' })
    if (path === '/api/settings') return json({ allow_external_ai: false })
    if (path === '/api/credentials?limit=100') return json({ items: [] })
    throw new Error('Unexpected fixture request: ' + path)
  })
  vi.stubGlobal('fetch', fetcher)
  return fetcher
}

it('keeps a later text/action draft when initial receipt selection completes late', async () => {
  const late = deferred()
  server((path) =>
    path === '/api/chat/sources/seed' ? late.promise : undefined,
  )
  render(<ChatPanel csrfToken="csrf" initialReceiptSourceId="seed" />)
  const user = userEvent.setup()
  await screen.findByRole('button', { name: 'Main conversation' })
  await user.selectOptions(screen.getByLabelText('Action'), 'save')
  await user.type(
    screen.getByLabelText('Memory to save'),
    'Keep my later draft.',
  )
  await act(async () =>
    late.release(
      json({
        id: 'seed',
        text: 'Old selected receipt text.',
        note: { is_current: true },
      }),
    ),
  )
  expect(screen.getByLabelText('Action')).toHaveValue('save')
  expect(screen.getByLabelText('Memory to save')).toHaveValue(
    'Keep my later draft.',
  )
})

it('does not restart a dismissed initial note when request/session props refresh', async () => {
  const late = deferred()
  let reads = 0
  server((path) =>
    path === '/api/chat/sources/seed'
      ? ++reads === 1
        ? late.promise
        : Promise.resolve(
            json({
              id: 'seed',
              text: 'Old seeded note.',
              note: { is_current: true },
            }),
          )
      : undefined,
  )
  const view = render(
    <ChatPanel csrfToken="csrf" initialReceiptSourceId="seed" />,
  )
  const user = userEvent.setup()
  await screen.findByRole('button', { name: 'Main conversation' })
  await user.selectOptions(screen.getByLabelText('Action'), 'save')
  await user.type(
    screen.getByLabelText('Memory to save'),
    'Draft survives refresh.',
  )
  await act(async () =>
    view.rerender(
      <ChatPanel csrfToken="refreshed" initialReceiptSourceId="seed" />,
    ),
  )
  expect(reads).toBe(1)
  expect(screen.getByLabelText('Memory to save')).toHaveValue(
    'Draft survives refresh.',
  )
})

it.each([200, 503])(
  'discards initial receipt completion (%s) after New conversation',
  async (status) => {
    const late = deferred()
    server((path) =>
      path === '/api/chat/sources/seed' ? late.promise : undefined,
    )
    render(<ChatPanel csrfToken="csrf" initialReceiptSourceId="seed" />)
    const user = userEvent.setup()
    await user.click(
      await screen.findByRole('button', { name: 'New conversation' }),
    )
    await act(async () =>
      late.release(
        json(
          {
            id: 'seed',
            text: 'Old selected receipt text.',
            note: { is_current: true },
          },
          status,
        ),
      ),
    )
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(
      screen.queryByDisplayValue('Old selected receipt text.'),
    ).not.toBeInTheDocument()
  },
)

it.each([200, 503])(
  'keeps saved Chat usable while daily usage is slow (%s)',
  async (status) => {
    const late = deferred()
    let reads = 0
    server((path) =>
      path === '/api/chat/usage' && ++reads > 1 ? late.promise : undefined,
    )
    render(<ChatPanel csrfToken="csrf" />)
    const user = userEvent.setup()
    await user.click(
      await screen.findByRole('button', { name: 'Main conversation' }),
    )
    await user.type(
      screen.getByLabelText('Memory to save'),
      'Synthetic saved note.',
    )
    await user.click(screen.getByRole('button', { name: 'Save memory' }))
    expect(await screen.findByText('Saved marker')).toBeVisible()
    expect(
      screen.getByRole('button', { name: 'New conversation' }),
    ).toBeEnabled()
    await user.click(screen.getByRole('button', { name: 'New conversation' }))
    await act(async () => late.release(json({ requests: 20 }, status)))
    expect(
      screen.queryByText(/Request saved. Daily usage/),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  },
)

it('serializes conversation paging and appends each conversation only once', async () => {
  const late = deferred()
  const fetcher = server((path) =>
    path === '/api/chat/conversations?cursor=page-two'
      ? late.promise
      : undefined,
  )
  render(<ChatPanel csrfToken="csrf" />)
  const user = userEvent.setup()
  await user.dblClick(
    await screen.findByRole('button', { name: 'More conversations' }),
  )
  expect(
    fetcher.mock.calls.filter(([path]) => path.endsWith('cursor=page-two')),
  ).toHaveLength(1)
  expect(
    screen.getByRole('button', { name: 'More conversations' }),
  ).toBeDisabled()
  await act(async () =>
    late.release(
      json({
        items: [
          { id: 'main', title: 'Main conversation' },
          { id: 'older', title: 'Older conversation' },
        ],
        next_cursor: null,
      }),
    ),
  )
  expect(
    await screen.findByRole('button', { name: 'Older conversation' }),
  ).toBeVisible()
  expect(
    screen.getAllByRole('button', { name: 'Main conversation' }),
  ).toHaveLength(1)
})

it('does not show a paging error in a new conversation', async () => {
  const late = deferred()
  server((path) =>
    path.includes('cursor=page-two') ? late.promise : undefined,
  )
  render(<ChatPanel csrfToken="csrf" />)
  const user = userEvent.setup()
  await user.click(
    await screen.findByRole('button', { name: 'More conversations' }),
  )
  await user.click(screen.getByRole('button', { name: 'New conversation' }))
  await act(async () => late.release(json({}, 503)))
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(
    screen.getByRole('button', { name: 'More conversations' }),
  ).toBeEnabled()
})
