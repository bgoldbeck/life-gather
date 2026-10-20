import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { MaintenancePanel } from './MaintenancePanel'

afterEach(() => vi.unstubAllGlobals())

function fixture() {
  const revisions: Record<string, unknown>[] = []
  let current: Record<string, unknown> | null = null
  let stale = false
  const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
    const url = new URL(path, 'https://synthetic.test')
    const body = JSON.parse(String(init?.body ?? '{}'))
    const response = (data: unknown, status = 200) =>
      new Response(JSON.stringify(data), { status })
    if (url.pathname === '/api/maintenance' && init?.method === 'POST') {
      const revision = {
        ...body,
        id: 'revision-1',
        source_id: 'source-1',
        previous_id: null,
        recorded_at: 1000000,
        superseded_at: null,
        origin: null,
      }
      revisions.push(revision)
      current = {
        id: 'task',
        entity_id: 'vehicle',
        target: { id: 'vehicle', name: 'Synthetic vehicle', kind: 'asset' },
        revision,
        state_token: 'a'.repeat(64),
        due_status: body.due_on ? 'upcoming' : 'unscheduled',
        local_today: '2026-10-19',
      }
      return response({ id: 'task', revision_id: 'revision-1' })
    }
    if (url.pathname === '/api/maintenance/revise') {
      if (stale) return response({ detail: 'private server detail' }, 409)
      const revision = {
        ...body,
        id: 'revision-2',
        source_id: 'source-2',
        previous_id: 'revision-1',
        recorded_at: 2000000,
        superseded_at: null,
        origin: null,
      }
      revisions.push(revision)
      current = {
        ...current,
        revision,
        state_token: 'b'.repeat(64),
        due_status: body.state,
      }
      return response({ id: 'task', revision_id: 'revision-2' })
    }
    if (url.pathname === '/api/maintenance/task') return response(current)
    if (url.pathname.endsWith('/history'))
      return response({ items: revisions, next_cursor: null })
    if (url.pathname.startsWith('/api/chat/sources/'))
      return response({
        id: 'source-1',
        text: 'Original synthetic maintenance statement.',
        next_offset: null,
      })
    if (url.pathname === '/api/maintenance') {
      const state = url.searchParams.get('state') ?? 'open'
      const revision = current?.revision as { state: string } | undefined
      return response({
        items:
          current && (state === 'all' || revision?.state === state)
            ? [current]
            : [],
        next_cursor: null,
      })
    }
    throw new Error('Unexpected synthetic request: ' + path)
  })
  vi.stubGlobal('fetch', fetcher)
  return {
    fetcher,
    setStale: () => {
      stale = true
    },
  }
}

async function createTask(user: ReturnType<typeof userEvent.setup>) {
  await user.click(
    await screen.findByRole('button', { name: 'Add maintenance task' }),
  )
  await user.type(screen.getByLabelText('Task title'), 'Replace cabin filter')
  await user.clear(screen.getByLabelText('Date timezone'))
  await user.type(screen.getByLabelText('Date timezone'), 'America/Los_Angeles')
  await user.type(
    screen.getByLabelText('Source statement'),
    'I chose this task; its due date is unknown.',
  )
  await user.click(
    screen.getByRole('button', { name: 'Save maintenance task' }),
  )
  await screen.findByText('Maintenance task saved with its original statement.')
}

it('creates an explicitly undated task, completes it and retains source/history', async () => {
  const user = userEvent.setup()
  const { fetcher } = fixture()
  render(<MaintenancePanel entityId="vehicle" csrfToken="csrf" />)
  await createTask(user)
  expect(
    screen.getByRole('combobox', { name: 'Maintenance state filter' }),
  ).toHaveValue('all')
  const posted = fetcher.mock.calls.find(([, init]) => init?.method === 'POST')!
  expect(JSON.parse(String(posted[1]?.body))).toMatchObject({
    entity_id: 'vehicle',
    due_on: null,
    completed_on: null,
    state: 'open',
    timezone: 'America/Los_Angeles',
  })
  expect(posted[1]?.headers).toMatchObject({ 'X-CSRF-Token': 'csrf' })
  await user.click(
    await screen.findByRole('button', { name: 'Edit Replace cabin filter' }),
  )
  await user.selectOptions(
    await screen.findByLabelText('Task state'),
    'completed',
  )
  expect(screen.getByLabelText('Completion date is known')).not.toBeChecked()
  await user.type(
    screen.getByLabelText('Source statement'),
    'Completed; the actual completion date is unknown.',
  )
  await user.click(
    screen.getByRole('button', { name: 'Save maintenance task' }),
  )
  await waitFor(() =>
    expect(screen.queryByLabelText('Task title')).not.toBeInTheDocument(),
  )
  await user.selectOptions(
    screen.getByLabelText('Maintenance state filter'),
    'all',
  )
  await user.click(
    await screen.findByRole('button', {
      name: 'History of Replace cabin filter',
    }),
  )
  const history = await screen.findByRole('region', {
    name: 'Maintenance history',
  })
  expect(within(history).getByText('Open')).toBeVisible()
  expect(within(history).getByText('Completed')).toBeVisible()
  await user.click(
    within(history).getAllByRole('button', { name: 'Open revision source' })[0],
  )
  await screen.findByText('Original synthetic maintenance statement.')
})

it('preserves a stale edit draft and requires an explicit discard/reload before saving again', async () => {
  const user = userEvent.setup()
  const server = fixture()
  render(<MaintenancePanel entityId="vehicle" csrfToken="csrf" />)
  await createTask(user)
  await user.click(
    await screen.findByRole('button', { name: 'Edit Replace cabin filter' }),
  )
  await user.type(
    await screen.findByLabelText('Source statement'),
    'My unsaved correction.',
  )
  server.setStale()
  await user.click(
    screen.getByRole('button', { name: 'Save maintenance task' }),
  )
  await screen.findByText(
    'This task changed. Your draft is preserved. Discard it and reload before editing again.',
  )
  expect(screen.getByLabelText('Source statement')).toHaveValue(
    'My unsaved correction.',
  )
  expect(
    screen.getByRole('button', { name: 'Save maintenance task' }),
  ).toBeDisabled()
  expect(screen.queryByText('private server detail')).not.toBeInTheDocument()
  await user.click(
    screen.getByRole('button', { name: 'Discard draft and reload task' }),
  )
  await waitFor(() =>
    expect(screen.getByLabelText('Source statement')).toHaveValue(''),
  )
})

async function seeded() {
  const server = fixture()
  await server.fetcher('/api/maintenance', {
    method: 'POST',
    body: JSON.stringify({
      title: 'Replace cabin filter',
      due_on: null,
      timezone: 'UTC',
      state: 'open',
      completed_on: null,
      text: 'Synthetic manual plan.',
    }),
  })
  const original = server.fetcher.getMockImplementation()!
  const task = await (await original('/api/maintenance/task')).json()
  return { ...server, original, task }
}

it('offers the actual linked profile from the global read-only view', async () => {
  const user = userEvent.setup()
  await seeded()
  const open = vi.fn()
  render(<MaintenancePanel csrfToken="csrf" onOpenProfile={open} />)
  await screen.findByText('Replace cabin filter')
  expect(
    screen.queryByRole('button', { name: 'Add maintenance task' }),
  ).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Manage in Profiles' }))
  expect(open).toHaveBeenCalledWith('vehicle')
})

it('aborts an old profile read and ignores its response after selecting another record', async () => {
  const server = await seeded()
  let resolve: (value: Response) => void = () => {}
  const late = new Promise<Response>((done) => {
    resolve = done
  })
  server.fetcher.mockImplementation(async (path, init) =>
    path.includes('entity_id=vehicle')
      ? late
      : path.includes('entity_id=other')
        ? new Response(JSON.stringify({ items: [], next_cursor: null }))
        : server.original(path, init),
  )
  const view = render(<MaintenancePanel entityId="vehicle" csrfToken="csrf" />)
  await waitFor(() =>
    expect(
      server.fetcher.mock.calls.some(([path]) =>
        path.includes('entity_id=vehicle'),
      ),
    ).toBe(true),
  )
  view.rerender(<MaintenancePanel entityId="other" csrfToken="csrf" />)
  await screen.findByText('No maintenance tasks in this view.')
  expect(
    server.fetcher.mock.calls.find(([path]) =>
      path.includes('entity_id=vehicle'),
    )?.[1]?.signal?.aborted,
  ).toBe(true)
  await act(async () => {
    resolve(
      new Response(JSON.stringify({ items: [server.task], next_cursor: null })),
    )
    await late
  })
  expect(screen.queryByText('Replace cabin filter')).not.toBeInTheDocument()
})

it('does not restore a previous filter from delayed pagination', async () => {
  const user = userEvent.setup()
  const server = await seeded()
  let resolve: (value: Response) => void = () => {}
  const late = new Promise<Response>((done) => {
    resolve = done
  })
  server.fetcher.mockImplementation(async (path, init) => {
    const url = new URL(path, 'https://synthetic.test')
    if (url.pathname === '/api/maintenance') {
      if (url.searchParams.get('cursor') === 'later') return late
      return new Response(
        JSON.stringify({
          items: url.searchParams.get('state') === 'all' ? [server.task] : [],
          next_cursor: url.searchParams.get('state') === 'all' ? 'later' : null,
        }),
      )
    }
    return server.original(path, init)
  })
  render(<MaintenancePanel entityId="vehicle" csrfToken="csrf" />)
  await user.click(
    await screen.findByRole('button', { name: 'More maintenance tasks' }),
  )
  await user.selectOptions(
    screen.getByLabelText('Maintenance state filter'),
    'completed',
  )
  await screen.findByText('No maintenance tasks in this view.')
  expect(
    server.fetcher.mock.calls.find(([path]) =>
      path.includes('cursor=later'),
    )?.[1]?.signal?.aborted,
  ).toBe(true)
  await act(async () => {
    resolve(
      new Response(JSON.stringify({ items: [server.task], next_cursor: null })),
    )
    await late
  })
  expect(screen.queryByText('Replace cabin filter')).not.toBeInTheDocument()
})

it('refuses to edit a response belonging to a different task', async () => {
  const user = userEvent.setup()
  const server = await seeded()
  server.fetcher.mockImplementation(async (path, init) =>
    path === '/api/maintenance/task'
      ? new Response(JSON.stringify({ ...server.task, id: 'different-task' }))
      : server.original(path, init),
  )
  render(<MaintenancePanel entityId="vehicle" csrfToken="csrf" />)
  await user.click(
    await screen.findByRole('button', { name: 'Edit Replace cabin filter' }),
  )
  await screen.findByText(
    'Unable to open this task for editing. Refresh the list or sign in again.',
  )
  expect(screen.queryByLabelText('Task title')).not.toBeInTheDocument()
})
