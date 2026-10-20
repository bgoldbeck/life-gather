import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { MaintenanceEditor } from './MaintenanceEditor'
import { MaintenanceError, type MaintenanceTask } from './maintenanceTypes'

const task: MaintenanceTask = {
  id: 'task',
  entity_id: 'vehicle',
  target: { id: 'vehicle', name: 'Synthetic vehicle', kind: 'asset' },
  revision: {
    id: 'revision',
    title: 'Synthetic task',
    due_on: null,
    completed_on: null,
    timezone: 'UTC',
    state: 'open',
    source_id: 'source',
    previous_id: null,
    recorded_at: 1000000,
    superseded_at: null,
  },
  state_token: 'a'.repeat(64),
  due_status: 'unscheduled',
  local_today: '2026-10-19',
}

async function fill(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Task title'), 'Synthetic task')
  await user.type(
    screen.getByLabelText('Source statement'),
    'My original synthetic statement.',
  )
}

it('prevents duplicate submits and retains one request identity after a lost response', async () => {
  const user = userEvent.setup()
  let reject: (reason: Error) => void = () => {}
  const first = new Promise<unknown>((_resolve, fail) => {
    reject = fail
  })
  const request = vi.fn(async (_path: string, _init?: RequestInit) =>
    request.mock.calls.length === 1
      ? first
      : { id: 'task', revision_id: 'revision' },
  )
  const onSaved = vi.fn()
  render(
    <MaintenanceEditor
      task={null}
      entityId="vehicle"
      request={request}
      onSaved={onSaved}
      onCancel={vi.fn()}
      onReload={vi.fn()}
    />,
  )
  await fill(user)
  await user.dblClick(
    screen.getByRole('button', { name: 'Save maintenance task' }),
  )
  expect(request).toHaveBeenCalledTimes(1)
  await act(async () => {
    reject(new Error('Synthetic lost response'))
    await first.catch(() => {})
  })
  await screen.findByText(
    'Unable to save this task. Check the dates, timezone and source statement, then retry.',
  )
  expect(screen.getByLabelText('Source statement')).toHaveValue(
    'My original synthetic statement.',
  )
  await user.click(
    screen.getByRole('button', { name: 'Save maintenance task' }),
  )
  expect(request).toHaveBeenCalledTimes(2)
  expect(request.mock.calls[0][1]?.body).toBe(request.mock.calls[1][1]?.body)
  expect(onSaved).toHaveBeenCalledTimes(1)
})

it('sends explicitly entered calendar dates and completion without inventing defaults', async () => {
  const user = userEvent.setup()
  const request = vi.fn(async (_path: string, _init?: RequestInit) => ({
    id: 'task',
    revision_id: 'revision',
  }))
  render(
    <MaintenanceEditor
      task={null}
      entityId="vehicle"
      request={request}
      onSaved={vi.fn()}
      onCancel={vi.fn()}
      onReload={vi.fn()}
    />,
  )
  await fill(user)
  expect(screen.queryByLabelText('Due date')).not.toBeInTheDocument()
  await user.click(screen.getByLabelText('Due date is known'))
  expect(screen.getByLabelText('Due date')).toHaveValue('')
  fireEvent.change(screen.getByLabelText('Due date'), {
    target: { value: '2028-02-29' },
  })
  await user.selectOptions(screen.getByLabelText('Task state'), 'completed')
  await user.click(screen.getByLabelText('Completion date is known'))
  expect(screen.getByLabelText('Completion date')).toHaveValue('')
  fireEvent.change(screen.getByLabelText('Completion date'), {
    target: { value: '2028-02-28' },
  })
  await user.click(
    screen.getByRole('button', { name: 'Save maintenance task' }),
  )
  expect(JSON.parse(String(request.mock.calls[0][1]?.body))).toMatchObject({
    due_on: '2028-02-29',
    completed_on: '2028-02-28',
    state: 'completed',
  })
})

it('aborts an unmounted save and ignores its delayed acknowledgement', async () => {
  const user = userEvent.setup()
  let resolve: (value: unknown) => void = () => {}
  const pending = new Promise<unknown>((done) => {
    resolve = done
  })
  const request = vi.fn(async (_path: string, _init?: RequestInit) => pending)
  const onSaved = vi.fn()
  const view = render(
    <MaintenanceEditor
      task={null}
      entityId="vehicle"
      request={request}
      onSaved={onSaved}
      onCancel={vi.fn()}
      onReload={vi.fn()}
    />,
  )
  await fill(user)
  await user.click(
    screen.getByRole('button', { name: 'Save maintenance task' }),
  )
  view.unmount()
  expect(request.mock.calls[0][1]?.signal?.aborted).toBe(true)
  await act(async () => {
    resolve({ id: 'task', revision_id: 'revision' })
    await pending
  })
  expect(onSaved).not.toHaveBeenCalled()
})

it.each([null, { id: 'wrong-task', revision_id: 'revision' }, { id: 'task' }])(
  'refuses an invalid or different-task acknowledgement: %j',
  async (result) => {
    const user = userEvent.setup()
    const request = vi.fn(async () => result)
    const onSaved = vi.fn()
    render(
      <MaintenanceEditor
        task={task}
        entityId="vehicle"
        request={request}
        onSaved={onSaved}
        onCancel={vi.fn()}
        onReload={vi.fn()}
      />,
    )
    await user.type(
      screen.getByLabelText('Source statement'),
      'My correction must target this task.',
    )
    await user.click(
      screen.getByRole('button', { name: 'Save maintenance task' }),
    )
    await screen.findByText(
      'Unable to save this task. Check the dates, timezone and source statement, then retry.',
    )
    expect(onSaved).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Source statement')).toHaveValue(
      'My correction must target this task.',
    )
  },
)

it('keeps an expired-session draft available for sign-in and retry', async () => {
  const user = userEvent.setup()
  const request = vi.fn(async () => {
    throw new MaintenanceError(401)
  })
  render(
    <MaintenanceEditor
      task={null}
      entityId="vehicle"
      request={request}
      onSaved={vi.fn()}
      onCancel={vi.fn()}
      onReload={vi.fn()}
    />,
  )
  await fill(user)
  await user.click(
    screen.getByRole('button', { name: 'Save maintenance task' }),
  )
  await screen.findByText(
    'Your session expired. Sign in again before saving this task.',
  )
  expect(screen.getByLabelText('Source statement')).toHaveValue(
    'My original synthetic statement.',
  )
})

it.each(['open', 'canceled'])(
  'revises a completed task to %s without carrying its completion date forward',
  async (state) => {
    const user = userEvent.setup()
    const request = vi.fn(async (_path: string, _init?: RequestInit) => ({
      id: 'task',
      revision_id: 'next',
    }))
    const completed: MaintenanceTask = {
      ...task,
      revision: {
        ...task.revision,
        state: 'completed',
        completed_on: '2026-10-19',
      },
    }
    render(
      <MaintenanceEditor
        task={completed}
        entityId="vehicle"
        request={request}
        onSaved={vi.fn()}
        onCancel={vi.fn()}
        onReload={vi.fn()}
      />,
    )
    await user.selectOptions(screen.getByLabelText('Task state'), state)
    expect(screen.queryByLabelText('Completion date')).not.toBeInTheDocument()
    await user.type(
      screen.getByLabelText('Source statement'),
      'I am explicitly changing this completion statement.',
    )
    await user.click(
      screen.getByRole('button', { name: 'Save maintenance task' }),
    )
    expect(JSON.parse(String(request.mock.calls[0][1]?.body))).toMatchObject({
      state,
      completed_on: null,
      state_token: task.state_token,
    })
  },
)
