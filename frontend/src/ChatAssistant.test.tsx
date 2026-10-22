import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ChatPanel } from './ChatPanel'

afterEach(() => vi.unstubAllGlobals())

function mockServer(turn: unknown) {
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/chat/preferences')
      return new Response(
        JSON.stringify({ credential_id: 'openai', model: 'synthetic-model' }),
      )
    if (url === '/api/settings')
      return new Response(JSON.stringify({ allow_external_ai: true }))
    if (url.startsWith('/api/credentials'))
      return new Response(
        JSON.stringify({
          items: [
            {
              id: 'openai',
              kind: 'ai',
              provider: 'openai',
              label: 'Synthetic OpenAI',
            },
          ],
        }),
      )
    if (url === '/api/chat/usage')
      return new Response(JSON.stringify({ requests: 0, limit: 20 }))
    if (url === '/api/chat/conversations' && init?.method === 'POST')
      return new Response(
        JSON.stringify({ id: 'chat-1', title: 'New conversation' }),
      )
    if (url === '/api/chat/conversations')
      return new Response(JSON.stringify({ items: [], next_cursor: null }))
    if (url === '/api/chat/conversations/chat-1/turns')
      return new Response(JSON.stringify(turn))
    throw new Error('Unexpected request: ' + url)
  })
  vi.stubGlobal('fetch', fetcher)
  return fetcher
}

it('sends AI assistant requests with the chosen model and shows the saved receipt', async () => {
  const fetcher = mockServer({
    id: 'turn-1',
    request_id: 'r1',
    mode: 'assistant',
    text: 'I own a Makita drill, model DHP484.',
    state: 'complete',
    result: {
      text: 'Added Makita drill to your inventory as your statement.',
      provider: 'openai',
      model: 'synthetic-model',
      changed_entity_id: 'asset-1',
      navigation: {
        page: 'Assets',
        entity_id: 'asset-1',
        name: 'Makita drill',
      },
      sources: [
        { id: 'source-1', text: 'I own a Makita drill, model DHP484.' },
      ],
    },
  })
  const opened = vi.fn()
  const changed = vi.fn()
  render(
    <ChatPanel
      csrfToken="csrf"
      onOpenAsset={opened}
      onRecordChanged={changed}
    />,
  )
  await screen.findByText('A place for the details')
  await userEvent.selectOptions(screen.getByLabelText('Action'), 'assistant')
  expect(screen.getByLabelText('Model ID')).toHaveValue('synthetic-model')
  await userEvent.type(
    screen.getByLabelText('Message your assistant'),
    'I own a Makita drill, model DHP484.',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Send' }))
  expect(
    await screen.findByText(
      'Added Makita drill to your inventory as your statement.',
    ),
  ).toBeVisible()
  expect(screen.getByText(/You · AI assistant/)).toBeVisible()
  expect(
    screen.getByRole('button', { name: 'Open Makita drill' }),
  ).toBeVisible()
  expect(changed).toHaveBeenCalledWith('asset-1')
  const [, init] = fetcher.mock.calls.find(
    ([url, options]) =>
      url === '/api/chat/conversations/chat-1/turns' &&
      options?.method === 'POST',
  )!
  expect(JSON.parse(String(init?.body))).toMatchObject({
    mode: 'assistant',
    credential_id: 'openai',
    model: 'synthetic-model',
  })
})

it('keeps the local assistant clearly labeled as working without AI', async () => {
  mockServer({})
  render(<ChatPanel csrfToken="csrf" />)
  await screen.findByText('A place for the details')
  expect(
    screen.getByRole('option', { name: 'Local assistant (no AI)' }),
  ).toBeInTheDocument()
  expect(
    screen.getByRole('option', { name: 'AI assistant' }),
  ).toBeInTheDocument()
})
