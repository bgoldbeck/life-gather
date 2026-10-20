import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ConversationDelete } from './ConversationDelete'
import { ChatRequestError } from './chatRequest'

const preview = {
  format: 'lifegather-conversation-deletion/1',
  id: 'owned',
  title: 'Synthetic conversation',
  turn_count: 2,
  pending_count: 0,
  preview_token: 'a'.repeat(64),
}

function setup(
  request = vi.fn(
    async (path: string, _init?: RequestInit): Promise<unknown> =>
      path.endsWith('/delete') ? { id: 'owned', deleted: true } : preview,
  ),
) {
  const onDeleted = vi.fn(),
    onCancel = vi.fn()
  const view = render(
    <ConversationDelete
      id="owned"
      title={preview.title}
      request={request}
      onDeleted={onDeleted}
      onCancel={onCancel}
    />,
  )
  return { request, onDeleted, onCancel, ...view }
}

describe('Reviewed conversation deletion', () => {
  it('loads exact scope before explicit confirmation and supports cancel', async () => {
    const user = userEvent.setup()
    const { request, onDeleted, onCancel } = setup()
    await screen.findByText('2 saved requests and their replies.')
    expect(screen.getByText(/Saved memories, profile changes/)).toBeVisible()
    expect(
      screen.getByRole('button', { name: 'Delete permanently' }),
    ).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Cancel deletion' }))
    expect(onCancel).toHaveBeenCalledOnce()
    expect(request).toHaveBeenCalledTimes(1)
    await user.click(
      screen.getByRole('checkbox', {
        name: 'Permanently delete this conversation',
      }),
    )
    await user.click(screen.getByRole('button', { name: 'Delete permanently' }))
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith('owned'))
    expect(request).toHaveBeenLastCalledWith(
      '/conversations/owned/delete',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          preview_token: preview.preview_token,
          confirmed: true,
        }),
      }),
    )
  })

  it('stops pending requests separately and requires the new preview token', async () => {
    const user = userEvent.setup()
    const refreshed = { ...preview, preview_token: 'b'.repeat(64) }
    const request = vi.fn(
      async (path: string, _init?: RequestInit): Promise<unknown> =>
        path.endsWith('/deletion-preview')
          ? { ...preview, pending_count: 1 }
          : path.endsWith('/stop-pending')
            ? refreshed
            : { id: 'owned', deleted: true },
    )
    setup(request)
    await screen.findByText(/1 pending chat request needs/)
    expect(screen.getByRole('checkbox')).toBeDisabled()
    await user.click(
      screen.getByRole('button', { name: 'Stop pending chat requests' }),
    )
    await screen.findByText(/No pending chat requests remain/)
    expect(request).toHaveBeenCalledWith(
      '/conversations/owned/stop-pending',
      expect.objectContaining({
        body: JSON.stringify({ preview_token: preview.preview_token }),
      }),
    )
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    expect(
      screen.getByRole('button', { name: 'Delete permanently' }),
    ).toBeDisabled()
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Delete permanently' }))
    await waitFor(() =>
      expect(request).toHaveBeenLastCalledWith(
        '/conversations/owned/delete',
        expect.objectContaining({
          body: JSON.stringify({
            preview_token: refreshed.preview_token,
            confirmed: true,
          }),
        }),
      ),
    )
  })

  it('requires review again after a conflict and never retries deletion automatically', async () => {
    const user = userEvent.setup()
    let reads = 0
    const request = vi.fn(
      async (path: string, _init?: RequestInit): Promise<unknown> => {
        if (path.endsWith('/delete'))
          throw new ChatRequestError('private server text', 409)
        reads++
        return reads === 1
          ? preview
          : { ...preview, turn_count: 3, preview_token: 'b'.repeat(64) }
      },
    )
    setup(request)
    await screen.findByText('2 saved requests and their replies.')
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Delete permanently' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Conversation changed',
    )
    expect(screen.queryByText('private server text')).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Review again' }))
    await screen.findByText('3 saved requests and their replies.')
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    expect(
      request.mock.calls.filter(([path]) => path.endsWith('/delete')),
    ).toHaveLength(1)
  })

  it.each([
    { id: 'foreign' },
    { preview_token: 'bad' },
    { pending_count: 3 },
    { turn_count: -1 },
  ])('refuses malformed or wrong-record previews: %s', async (change) => {
    setup(vi.fn(async (): Promise<unknown> => ({ ...preview, ...change })))
    await screen.findByRole('alert')
    expect(
      screen.queryByRole('button', { name: 'Delete permanently' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })

  it('prevents duplicate mutation and ignores a late completion after unmount', async () => {
    const user = userEvent.setup()
    let resolve: ((value: unknown) => void) | undefined
    const deferred = new Promise<unknown>((done) => {
      resolve = done
    })
    const request = vi.fn(
      async (path: string, _init?: RequestInit): Promise<unknown> =>
        path.endsWith('/delete') ? deferred : preview,
    )
    const { unmount, onDeleted } = setup(request)
    await screen.findByText('2 saved requests and their replies.')
    await user.click(screen.getByRole('checkbox'))
    await user.dblClick(
      screen.getByRole('button', { name: 'Delete permanently' }),
    )
    expect(
      request.mock.calls.filter(([path]) => path.endsWith('/delete')),
    ).toHaveLength(1)
    const signal = request.mock.calls.at(-1)?.[1]?.signal
    expect(
      screen.getByRole('button', { name: 'Cancel deletion' }),
    ).toBeDisabled()
    unmount()
    expect(signal?.aborted).toBe(true)
    await act(async () => {
      resolve?.({ id: 'owned', deleted: true })
      await deferred
    })
    expect(onDeleted).not.toHaveBeenCalled()
  })

  it('ignores an old preview after switching the keyed target', async () => {
    let resolve: ((value: unknown) => void) | undefined
    const deferred = new Promise<unknown>((done) => {
      resolve = done
    })
    const request = vi.fn(
      async (path: string, _init?: RequestInit): Promise<unknown> =>
        path.includes('/owned/')
          ? deferred
          : { ...preview, id: 'other', title: 'Other synthetic' },
    )
    const { rerender, onDeleted, onCancel } = setup(request)
    const oldSignal = request.mock.calls[0][1]?.signal
    rerender(
      <ConversationDelete
        key="other"
        id="other"
        title="Other synthetic"
        request={request}
        onDeleted={onDeleted}
        onCancel={onCancel}
      />,
    )
    await screen.findByRole('heading', {
      name: 'Delete conversation: Other synthetic',
    })
    expect(oldSignal?.aborted).toBe(true)
    await act(async () => {
      resolve?.(preview)
      await deferred
    })
    expect(
      screen.queryByText('Delete conversation: Synthetic conversation'),
    ).not.toBeInTheDocument()
  })

  it('handles expired sessions and invalid deletion acknowledgements without clearing history', async () => {
    const user = userEvent.setup()
    const request = vi.fn(
      async (path: string, _init?: RequestInit): Promise<unknown> =>
        path.endsWith('/delete') ? { id: 'foreign', deleted: true } : preview,
    )
    const { onDeleted, unmount } = setup(request)
    await screen.findByText('2 saved requests and their replies.')
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Delete permanently' }))
    await screen.findByRole('alert')
    expect(onDeleted).not.toHaveBeenCalled()
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    unmount()
    setup(
      vi.fn(async (): Promise<unknown> => {
        throw new ChatRequestError('expired', 401)
      }),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'session expired',
    )
  })
})
