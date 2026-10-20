import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { MaintenanceHistory } from './MaintenanceHistory'
import type { MaintenanceRevision } from './maintenanceTypes'

const original: MaintenanceRevision = {
  id: 'first',
  title: 'Synthetic task',
  due_on: null,
  timezone: 'UTC',
  state: 'open',
  completed_on: null,
  source_id: 'source-first',
  previous_id: null,
  recorded_at: 1000000,
  superseded_at: 2000000,
  origin: { method: 'manual_entry', interface: 'web' },
}

it('pages through original revisions and opens the source belonging to that revision', async () => {
  const user = userEvent.setup()
  const request = vi.fn(async (path: string) =>
    path.includes('?cursor=first')
      ? {
          items: [
            {
              ...original,
              id: 'second',
              state: 'completed',
              source_id: 'source-second',
              previous_id: 'first',
              recorded_at: 2000000,
              superseded_at: null,
            },
          ],
          next_cursor: null,
        }
      : { items: [original], next_cursor: 'first' },
  )
  const openSource = vi.fn(async () => {})
  render(
    <MaintenanceHistory
      taskId="task"
      request={request}
      onOpenSource={openSource}
    />,
  )
  await screen.findByText('Open')
  await user.click(
    screen.getByRole('button', { name: 'More maintenance history' }),
  )
  await screen.findByText('Completed')
  expect(screen.getByText('Open')).toBeVisible()
  expect(screen.getAllByText('manual entry · web.')).toHaveLength(2)
  await user.click(
    screen.getAllByRole('button', { name: 'Open revision source' })[1],
  )
  expect(openSource).toHaveBeenCalledWith('source-second')
  expect(request.mock.calls[1][0]).toContain('cursor=first')
})

it.each([
  null,
  { items: null, next_cursor: null },
  { items: [{ ...original, source_id: null }], next_cursor: null },
])('shows a recoverable error for malformed history: %j', async (page) => {
  const request = vi.fn(async () => page)
  render(
    <MaintenanceHistory
      taskId="task"
      request={request}
      onOpenSource={vi.fn(async () => {})}
    />,
  )
  await screen.findByText('Unable to load maintenance history.')
  expect(
    screen.getByRole('button', { name: 'Retry maintenance history' }),
  ).toBeEnabled()
})
