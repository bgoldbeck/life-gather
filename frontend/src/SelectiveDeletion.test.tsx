import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { BulkDelete } from './BulkDelete'
import { RetentionSettings } from './RetentionSettings'

afterEach(() => vi.unstubAllGlobals())

const items = [
  { id: 'p-1', label: 'first.jpg', updated_at: 11 },
  { id: 'p-2', label: 'second.jpg', updated_at: 12 },
  { id: 'p-3', label: 'third.jpg', updated_at: 13 },
]

it('deletes only the chosen photos after acknowledgement', async () => {
  const request = vi.fn().mockResolvedValue({ deleted_count: 2 })
  const onDeleted = vi.fn()
  render(
    <BulkDelete
      kind="photos"
      items={items}
      request={request}
      onDeleted={onDeleted}
    />,
  )
  await userEvent.click(screen.getByText('Delete several photos'))
  const button = screen.getByRole('button', {
    name: 'Delete 0 selected permanently',
  })
  expect(button).toBeDisabled()
  await userEvent.click(screen.getByLabelText('first.jpg'))
  await userEvent.click(screen.getByLabelText('third.jpg'))
  const ready = screen.getByRole('button', {
    name: 'Delete 2 selected permanently',
  })
  expect(ready).toBeDisabled()
  await userEvent.click(
    screen.getByLabelText(
      'I understand these originals cannot be recovered here',
    ),
  )
  await userEvent.click(ready)
  expect(request).toHaveBeenCalledWith('photos/delete-many', {
    method: 'POST',
    body: JSON.stringify({
      photos: [
        { photo_id: 'p-1', expected_updated_at: 11 },
        { photo_id: 'p-3', expected_updated_at: 13 },
      ],
    }),
  })
  expect(onDeleted).toHaveBeenCalledWith(['p-1', 'p-3'])
  expect(await screen.findByRole('status')).toHaveTextContent(
    '2 photo(s) deleted',
  )
})

it('reports a refused document batch without claiming deletion', async () => {
  const request = vi.fn().mockRejectedValue(new Error('409'))
  const onDeleted = vi.fn()
  render(
    <BulkDelete
      kind="documents"
      items={[{ id: 'd-1', label: 'manual.pdf', updated_at: 5 }]}
      request={request}
      onDeleted={onDeleted}
    />,
  )
  await userEvent.click(screen.getByText('Delete several documents'))
  await userEvent.click(screen.getByLabelText('manual.pdf'))
  await userEvent.click(
    screen.getByLabelText(
      'I understand these originals cannot be recovered here',
    ),
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Delete 1 selected permanently' }),
  )
  expect(request.mock.calls[0][0]).toBe('documents/delete-many')
  expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({
    documents: [{ document_id: 'd-1', expected_updated_at: 5 }],
  })
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Nothing was deleted',
  )
  expect(onDeleted).not.toHaveBeenCalled()
})

it('previews and saves conversation retention', async () => {
  const fetch = vi.fn(async (path: string, init?: RequestInit) => {
    if (init?.method === 'PUT')
      return {
        ok: true,
        json: async () => ({ conversation_days: 90, deleted_count: 3 }),
      }
    if (path.endsWith('?preview_days=90'))
      return {
        ok: true,
        json: async () => ({
          conversation_days: null,
          preview: { conversation_days: 90, eligible_count: 3 },
        }),
      }
    return {
      ok: true,
      json: async () => ({
        conversation_days: null,
        preview: { conversation_days: null, eligible_count: 0 },
      }),
    }
  })
  vi.stubGlobal('fetch', fetch)
  render(<RetentionSettings csrfToken="csrf" />)
  const select = screen.getByLabelText('Keep conversations')
  await waitFor(() => expect(select).toBeEnabled())
  expect(screen.getByRole('button', { name: 'Save retention' })).toBeDisabled()
  await userEvent.selectOptions(select, '90')
  expect(await screen.findByRole('status')).toHaveTextContent(
    'Saving now deletes 3 conversation(s)',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Save retention' }))
  const put = fetch.mock.calls.find(([, init]) => init?.method === 'PUT')!
  expect(put[0]).toBe('/api/chat/retention')
  expect(put[1]?.body).toBe(JSON.stringify({ conversation_days: 90 }))
  expect(await screen.findByRole('status')).toHaveTextContent(
    '3 older conversation(s) deleted',
  )
})
