import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ChatPanel } from './ChatPanel'

afterEach(() => vi.unstubAllGlobals())

const rows = [
  { id: 'chat-1', title: 'First synthetic' },
  { id: 'chat-2', title: 'Second synthetic' },
]
const response = (value: unknown) => new Response(JSON.stringify(value))
function server(cursor: string | null = null) {
  const fetcher = vi.fn(
    async (url: string, _init?: RequestInit): Promise<Response> => {
      if (url === '/api/settings') return response({ allow_external_ai: false })
      if (url.startsWith('/api/credentials')) return response({ items: [] })
      if (url === '/api/chat/preferences')
        return response({ credential_id: '', model: '' })
      if (url === '/api/chat/usage') return response({ requests: 3, limit: 20 })
      if (url === '/api/chat/conversations')
        return response({ items: rows, next_cursor: cursor })
      if (url.endsWith('/chat-1/turns'))
        return response({
          items: [
            {
              id: 'turn',
              request_id: 'request',
              mode: 'save',
              text: 'Saved original note',
              state: 'complete',
              result: {
                text: 'Saved independently as evidence.',
                sources: [{ id: 'source', text: 'Original evidence' }],
              },
            },
          ],
          next_cursor: null,
        })
      const row = rows.find((value) =>
        url.includes(`/conversations/${value.id}/`),
      )
      if (row && url.endsWith('/deletion-preview'))
        return response({
          format: 'lifegather-conversation-deletion/1',
          ...row,
          turn_count: row.id === 'chat-1' ? 1 : 0,
          pending_count: 0,
          preview_token: 'a'.repeat(64),
        })
      if (row && url.endsWith('/delete'))
        return response({ id: row.id, deleted: true })
      throw new Error('Unexpected synthetic request: ' + url)
    },
  )
  vi.stubGlobal('fetch', fetcher)
  return fetcher
}

it.each(rows)(
  'deletes only $title and preserves the unsent draft and other conversation',
  async (target) => {
    const user = userEvent.setup()
    const fetcher = server()
    const { rerender } = render(<ChatPanel csrfToken="csrf" />)
    await user.click(
      await screen.findByRole('button', {
        name: 'First synthetic',
      }),
    )
    await screen.findByText('Saved independently as evidence.')
    await user.type(
      screen.getByLabelText('Memory to save'),
      'Unsent synthetic draft',
    )
    const label = `Review deletion of ${target.title}`
    await user.click(screen.getByRole('button', { name: label }))
    await screen.findByRole('checkbox', {
      name: 'Permanently delete this conversation',
    })
    expect(
      screen.getByRole('button', { name: 'New conversation' }),
    ).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Cancel deletion' }))
    expect(screen.getByLabelText('Memory to save')).toHaveValue(
      'Unsent synthetic draft',
    )
    expect(screen.getByRole('button', { name: label })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: label }))
    await user.click(
      await screen.findByRole('checkbox', {
        name: 'Permanently delete this conversation',
      }),
    )
    await user.click(screen.getByRole('button', { name: 'Delete permanently' }))
    await screen.findByText(
      'Conversation deleted. Other saved records were retained.',
    )
    expect(
      screen.queryByRole('button', { name: target.title }),
    ).not.toBeInTheDocument()
    expect(screen.getByLabelText('Memory to save')).toHaveValue(
      'Unsent synthetic draft',
    )
    if (target.id === 'chat-1')
      expect(
        screen.queryByText('Saved independently as evidence.'),
      ).not.toBeInTheDocument()
    else
      expect(screen.getByText('Saved independently as evidence.')).toBeVisible()
    const posted = fetcher.mock.calls.find(([url]) => url.endsWith('/delete'))!
    expect(posted[1]?.headers).toMatchObject({ 'X-CSRF-Token': 'csrf' })
    expect(JSON.parse(String(posted[1]?.body))).toEqual({
      preview_token: 'a'.repeat(64),
      confirmed: true,
    })
    // A metadata reload returning an old page cannot put the deleted entry back.
    rerender(<ChatPanel csrfToken="refreshed-csrf" />)
    await waitFor(() =>
      expect(
        fetcher.mock.calls.filter(([url]) => url === '/api/chat/conversations'),
      ).toHaveLength(2),
    )
    await waitFor(() =>
      expect(
        screen.getByRole('button', {
          name: target.id === 'chat-1' ? 'Second synthetic' : 'First synthetic',
        }),
      ).toBeEnabled(),
    )
    expect(
      screen.queryByRole('button', { name: target.title }),
    ).not.toBeInTheDocument()
    expect(screen.getByLabelText('Memory to save')).toHaveValue(
      'Unsent synthetic draft',
    )
  },
)

it('aborts pending pagination so a late page cannot restore a deleted conversation', async () => {
  const user = userEvent.setup()
  const fetcher = server('later')
  const original = fetcher.getMockImplementation()!
  let resolve: ((value: Response) => void) | undefined
  const late = new Promise<Response>((done) => {
    resolve = done
  })
  fetcher.mockImplementation(async (url, init) =>
    url.includes('?cursor=later') ? late : original(url, init),
  )
  render(<ChatPanel csrfToken="csrf" />)
  await screen.findByRole('button', { name: 'First synthetic' })
  await user.click(screen.getByRole('button', { name: 'More conversations' }))
  await user.click(
    screen.getByRole('button', { name: 'Review deletion of First synthetic' }),
  )
  await user.click(
    await screen.findByRole('checkbox', {
      name: 'Permanently delete this conversation',
    }),
  )
  await user.click(screen.getByRole('button', { name: 'Delete permanently' }))
  await screen.findByText(
    'Conversation deleted. Other saved records were retained.',
  )
  const signal = fetcher.mock.calls.find(([url]) =>
    url.includes('?cursor=later'),
  )?.[1]?.signal
  expect(signal?.aborted).toBe(true)
  await act(async () => {
    resolve?.(response({ items: rows, next_cursor: null }))
    await late
  })
  expect(
    screen.queryByRole('button', { name: 'First synthetic' }),
  ).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Second synthetic' })).toBeVisible()
})
