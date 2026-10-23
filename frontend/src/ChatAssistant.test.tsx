import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ChatPanel } from './ChatPanel'

afterEach(() => vi.unstubAllGlobals())

it('shows committed maintenance dates, refreshes the record and opens its maintenance view', async () => {
  const fetcher = mockServer({
    id: 'maintenance-turn',
    request_id: 'maintenance-request',
    mode: 'assistant',
    state: 'complete',
    text: 'Log completed oil change on my mower',
    result: {
      text: 'Recorded oil change for Synthetic mower as completed, as your statement.',
      changed_entity_id: 'mower',
      navigation: {
        page: 'Profiles',
        entity_id: 'mower',
        name: 'Synthetic mower',
      },
      maintenance: {
        task_id: 'task-1',
        revision_id: 'revision-1',
        title: 'oil change',
        state: 'completed',
        due_on: null,
        completed_on: null,
        timezone: 'America/Los_Angeles',
      },
    },
  })
  const open = vi.fn(),
    changed = vi.fn(),
    asset = vi.fn()
  render(
    <ChatPanel
      csrfToken="csrf"
      onOpenMaintenance={open}
      onRecordChanged={changed}
      onOpenAsset={asset}
    />,
  )
  await screen.findByText('A place for the details')
  await userEvent.selectOptions(screen.getByLabelText('Action'), 'assistant')
  await userEvent.type(
    screen.getByLabelText('Message your assistant'),
    'Log completed oil change on my mower',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Send' }))
  expect(await screen.findByText('Saved maintenance task')).toBeInTheDocument()
  expect(screen.getByText('Completion date: Unknown')).toBeInTheDocument()
  expect(screen.getByText('Due date: Unknown')).toBeInTheDocument()
  expect(changed).toHaveBeenCalledWith('mower')
  expect(open).toHaveBeenCalledWith('mower')
  expect(asset).not.toHaveBeenCalled()
  await userEvent.click(
    screen.getByRole('button', { name: 'Open Synthetic mower maintenance' }),
  )
  expect(open).toHaveBeenCalledTimes(2)
  const call = fetcher.mock.calls.find(([url]) => url.endsWith('/stream'))!
  expect(JSON.parse(call[1]!.body as string).timezone).toBe(
    Intl.DateTimeFormat().resolvedOptions().timeZone,
  )
})

it('puts an explicit task choice in the draft without treating a task ID as an asset', async () => {
  mockServer({
    id: 'maintenance-question',
    request_id: 'question',
    mode: 'assistant',
    state: 'complete',
    text: 'Mark my mower oil change complete',
    result: {
      text: 'Which oil change? No changes were saved.',
      maintenance_choices: [
        {
          id: 'abcd1234-1',
          name: 'oil change (task abcd1234)',
          asset_id: 'mower',
        },
      ],
    },
  })
  const asset = vi.fn()
  render(<ChatPanel csrfToken="csrf" onOpenAsset={asset} />)
  await screen.findByText('A place for the details')
  await userEvent.selectOptions(screen.getByLabelText('Action'), 'assistant')
  await userEvent.type(
    screen.getByLabelText('Message your assistant'),
    'Mark my mower oil change complete',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Send' }))
  await userEvent.click(
    await screen.findByRole('button', {
      name: 'Use oil change (task abcd1234)',
    }),
  )
  expect(screen.getByLabelText('Message your assistant')).toHaveValue(
    'Use oil change (task abcd1234)',
  )
  expect(asset).not.toHaveBeenCalled()
})

it('opens saved research on its asset without treating finding IDs as memory sources', async () => {
  const fetcher = mockServer({
    id: 'recall-turn',
    request_id: 'recall',
    mode: 'assistant',
    state: 'complete',
    text: 'What filter is in the saved manual?',
    result: {
      text: 'The saved manual lists AB-12 [Research 1]. No changes were saved.',
      saved_research: [
        {
          id: 'finding-1',
          citation: 1,
          asset_id: 'mower',
          asset_name: 'Garage mower',
          title: 'Synthetic manual',
          url: 'https://manufacturer.example/manual',
          published: null,
          researched_at: '2026-10-22T09:00:00Z',
          recorded_at: 1792660000000000,
          excerpt_kind: 'source',
          excerpts: ['AB-12'],
        },
      ],
    },
  })
  const open = vi.fn()
  render(<ChatPanel csrfToken="csrf" onOpenAsset={open} />)
  await screen.findByText('A place for the details')
  await userEvent.selectOptions(screen.getByLabelText('Action'), 'assistant')
  await userEvent.type(
    screen.getByLabelText('Message your assistant'),
    'What filter is in the saved manual?',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Send' }))
  await userEvent.click(
    await screen.findByRole('button', {
      name: 'Open Garage mower saved research',
    }),
  )
  expect(open).toHaveBeenCalledWith('mower')
  expect(
    fetcher.mock.calls.some(([url]) => url.includes('/sources/finding-1')),
  ).toBe(false)
})

function sse(...events: unknown[]) {
  return events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('')
}

/** A stream that sends host statuses, then the turn once `finish` is called. */
function statusStream(turn: unknown) {
  let finish = () => {}
  const encoder = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(
        encoder.encode(
          sse(
            { type: 'status', text: 'Checking your request…' },
            { type: 'status', text: 'Searching your assets…' },
          ),
        ),
      )
      finish = () => {
        controller.enqueue(encoder.encode(sse({ type: 'complete', turn })))
        controller.close()
      }
    },
  })
  return {
    response: new Response(body, {
      headers: { 'content-type': 'text/event-stream' },
    }),
    finish: () => finish(),
  }
}

function mockServer(turn: unknown, stream?: () => Response) {
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
    if (url === '/api/chat/conversations/chat-1/stream')
      return stream
        ? stream()
        : new Response(sse({ type: 'complete', turn }), {
            headers: { 'content-type': 'text/event-stream' },
          })
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
      url === '/api/chat/conversations/chat-1/stream' &&
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

it('shows host progress while the assistant works and the result only from the saved turn', async () => {
  const saved = {
    id: 'turn-2',
    request_id: 'r2',
    mode: 'assistant',
    text: 'What color is my bicycle?',
    state: 'complete',
    result: {
      text: "Your bicycle's paint is recorded as green. No changes were saved.",
      provider: 'openai',
      model: 'synthetic-model',
      sources: [],
    },
  }
  const stream = statusStream(saved)
  mockServer(saved, () => stream.response)
  render(<ChatPanel csrfToken="csrf" />)
  await screen.findByText('A place for the details')
  await userEvent.selectOptions(screen.getByLabelText('Action'), 'assistant')
  await userEvent.type(
    screen.getByLabelText('Message your assistant'),
    'What color is my bicycle?',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Send' }))
  expect(await screen.findByText('Searching your assets…')).toBeVisible()
  expect(screen.queryByText(/recorded as green/)).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Reply draft')).not.toBeInTheDocument()
  stream.finish()
  expect(await screen.findByText(/recorded as green/)).toBeVisible()
  expect(screen.queryByText('Searching your assets…')).not.toBeInTheDocument()
})
