import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ChatPanel } from './ChatPanel'
import { WorkspaceAssistant } from './WorkspaceAssistant'

afterEach(() => vi.unstubAllGlobals())
const context = {
  page: 'Assets',
  entity_id: 'truck',
  version: 'a'.repeat(64),
  name: 'Synthetic F150',
}
function mockServer(deferConversation = false) {
  let resolveCreate: ((value: Response) => void) | undefined
  let resolveTurn: ((value: Response) => void) | undefined
  let sent: Record<string, unknown> = {}
  const json = (data: unknown) => new Response(JSON.stringify(data))
  const fetcher = vi.fn(
    async (url: string, init?: RequestInit): Promise<Response> => {
      if (url === '/api/chat/context') return json(context)
      if (url === '/api/settings') return json({ allow_external_ai: false })
      if (url === '/api/chat/preferences')
        return json({ credential_id: '', model: '' })
      if (url === '/api/chat/usage') return json({ used: 0 })
      if (url === '/api/chat/conversations' && init?.method === 'POST') {
        if (deferConversation)
          return new Promise((resolve) => {
            resolveCreate = resolve
          })
        return json({ id: 'conversation', title: 'New conversation' })
      }
      if (url.endsWith('/turns') && init?.method === 'POST') {
        sent = JSON.parse(String(init.body))
        return new Promise((resolve) => {
          resolveTurn = resolve
        })
      }
      return json({ items: [], next_cursor: null })
    },
  )
  vi.stubGlobal('fetch', fetcher)
  return {
    fetcher,
    create: () =>
      resolveCreate?.(json({ id: 'conversation', title: 'New conversation' })),
    reply: () =>
      resolveTurn?.(
        json({
          id: 'turn',
          ...sent,
          state: 'complete',
          result: {
            text: 'Opening the truck.',
            navigation: {
              page: 'Assets',
              entity_id: 'truck',
              name: 'Synthetic F150',
            },
          },
        }),
      ),
    sent: () => sent,
  }
}

it('opens the uniquely resolved asset and retains an explicit open action', async () => {
  const server = mockServer()
  const open = vi.fn()
  render(
    <ChatPanel
      csrfToken="csrf"
      context={context}
      defaultMode="organize"
      onOpenAsset={open}
    />,
  )
  await screen.findByText('A place for the details')
  await userEvent.type(
    screen.getByLabelText('Message your assistant'),
    'Edit my F150',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Send' }))
  await waitFor(() =>
    expect(server.sent()).toHaveProperty('text', 'Edit my F150'),
  )
  await act(async () => server.reply())
  expect(open).toHaveBeenCalledExactlyOnceWith('truck')
  expect(
    screen.getByRole('button', { name: 'Open Synthetic F150' }),
  ).toBeVisible()
})

it('pins context before creating a conversation and avoids navigation from a late reply', async () => {
  const server = mockServer(true)
  const open = vi.fn()
  const { rerender } = render(
    <ChatPanel
      csrfToken="csrf"
      context={context}
      defaultMode="organize"
      onOpenAsset={open}
    />,
  )
  await screen.findByText('A place for the details')
  await userEvent.type(
    screen.getByLabelText('Message your assistant'),
    'Edit my F150',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Send' }))
  rerender(
    <ChatPanel
      csrfToken="csrf"
      context={{ page: 'Settings', entity_id: null, version: '' }}
      defaultMode="organize"
      onOpenAsset={open}
    />,
  )
  await act(async () => server.create())
  await waitFor(() => expect(server.sent()).toHaveProperty('context'))
  expect(server.sent().context).toEqual({
    page: 'Assets',
    entity_id: 'truck',
    version: 'a'.repeat(64),
  })
  await act(async () => server.reply())
  expect(open).not.toHaveBeenCalled()
  await userEvent.click(
    screen.getByRole('button', { name: 'Open Synthetic F150' }),
  )
  expect(open).toHaveBeenCalledExactlyOnceWith('truck')
})

it('blocks sending while the new record context is unavailable', async () => {
  const server = mockServer()
  const original = server.fetcher.getMockImplementation()!
  server.fetcher.mockImplementation((url, init) =>
    url === '/api/chat/context'
      ? Promise.resolve(new Response('', { status: 500 }))
      : original(url, init),
  )
  render(
    <WorkspaceAssistant
      page="Assets"
      entityId="truck"
      revision={0}
      csrfToken="csrf"
      onOpenAsset={vi.fn()}
      onOpenGraph={vi.fn()}
      onOpenScan={vi.fn()}
      onRecordChanged={vi.fn()}
    />,
  )
  await screen.findByText('A place for the details')
  await userEvent.type(
    screen.getByLabelText('Message your assistant'),
    'Set VIN to exact',
  )
  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
})
