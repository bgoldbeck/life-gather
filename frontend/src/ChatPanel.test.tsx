import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ChatPanel } from './ChatPanel'

afterEach(() => vi.unstubAllGlobals())

it('restores a Google Gemini connection and labels its completed reply', async () => {
  const fetcher = mockServer()
  const original = fetcher.getMockImplementation()!
  fetcher.mockImplementation(async (url, init) => {
    if (url === '/api/settings')
      return new Response(JSON.stringify({ allow_external_ai: true }))
    if (url.startsWith('/api/credentials'))
      return new Response(
        JSON.stringify({
          items: [
            {
              id: 'google',
              kind: 'ai',
              provider: 'google',
              label: 'Synthetic Google',
            },
          ],
        }),
      )
    if (url === '/api/chat/preferences')
      return new Response(
        JSON.stringify({ credential_id: 'google', model: 'gemini-synthetic' }),
      )
    if (url.endsWith('/stream'))
      return new Response(
        'data: ' +
          JSON.stringify({
            type: 'complete',
            turn: {
              id: 'google-turn',
              request_id: 'request',
              mode: 'ask',
              text: 'filter?',
              state: 'complete',
              result: {
                text: 'Synthetic Gemini reply.',
                provider: 'google',
                model: 'gemini-synthetic',
              },
            },
          }) +
          '\n\n',
        { headers: { 'content-type': 'text/event-stream' } },
      )
    return original(url, init)
  })
  render(<ChatPanel csrfToken="csrf" />)
  await screen.findByText('A place for the details')
  await userEvent.selectOptions(screen.getByLabelText('Action'), 'ask')
  expect(screen.getByLabelText('Model ID')).toHaveValue('gemini-synthetic')
  expect(
    screen.getByRole('option', { name: 'Synthetic Google · Google Gemini' }),
  ).toBeInTheDocument()
  await userEvent.type(screen.getByLabelText('Your question'), 'filter?')
  await userEvent.click(screen.getByRole('button', { name: 'Ask AI' }))
  expect(
    await screen.findByText('Google Gemini · gemini-synthetic'),
  ).toBeVisible()
  const [, init] = fetcher.mock.calls.find(([url]) => url.endsWith('/stream'))!
  expect(JSON.parse(String(init?.body))).toMatchObject({
    credential_id: 'google',
    model: 'gemini-synthetic',
  })
})

it('shows a transient draft and discards it when final validation fails', async () => {
  const fetcher = mockServer()
  const original = fetcher.getMockImplementation()!
  let controller: ReadableStreamDefaultController<Uint8Array> | undefined
  const encode = (value: unknown) =>
    new TextEncoder().encode('data: ' + JSON.stringify(value) + '\n\n')
  fetcher.mockImplementation(async (url, init) => {
    if (url === '/api/settings')
      return new Response(JSON.stringify({ allow_external_ai: true }))
    if (url.startsWith('/api/credentials'))
      return new Response(
        JSON.stringify({
          items: [
            { id: 'ai', kind: 'ai', provider: 'openai', label: 'Synthetic' },
          ],
        }),
      )
    if (url.endsWith('/stream'))
      return new Response(
        new ReadableStream({
          start(next) {
            controller = next
            next.enqueue(
              encode({ type: 'draft', text: 'Unvalidated synthetic draft' }),
            )
          },
        }),
        { headers: { 'content-type': 'text/event-stream' } },
      )
    return original(url, init)
  })
  render(<ChatPanel csrfToken="csrf" />)
  await screen.findByText('A place for the details')
  await userEvent.selectOptions(screen.getByLabelText('Action'), 'ask')
  await userEvent.selectOptions(screen.getByLabelText('AI connection'), 'ai')
  await userEvent.type(screen.getByLabelText('Model ID'), 'synthetic-model')
  await userEvent.type(screen.getByLabelText('Your question'), 'filter?')
  await userEvent.click(screen.getByRole('button', { name: 'Ask AI' }))
  expect(await screen.findByText('Unvalidated synthetic draft')).toBeVisible()
  expect(
    screen.getByText('Generating · draft not yet validated or saved'),
  ).toBeVisible()
  await act(async () => {
    controller!.enqueue(
      encode({
        type: 'complete',
        turn: {
          id: 'failed-turn',
          request_id: 'request',
          mode: 'ask',
          text: 'filter?',
          state: 'failed',
          result: { text: 'Unable to finish.' },
        },
      }),
    )
    controller!.close()
  })
  expect(await screen.findByText('Request failed')).toBeVisible()
  expect(
    screen.queryByText('Unvalidated synthetic draft'),
  ).not.toBeInTheDocument()
})

it('offers Claude beside OpenAI and sends only the selected connection and model', async () => {
  const user = userEvent.setup()
  const fetcher = mockServer()
  const original = fetcher.getMockImplementation()!
  fetcher.mockImplementation(async (url, init) => {
    if (url === '/api/settings')
      return new Response(JSON.stringify({ allow_external_ai: true }))
    if (url.startsWith('/api/credentials'))
      return new Response(
        JSON.stringify({
          items: [
            { id: 'openai', kind: 'ai', provider: 'openai', label: 'Primary' },
            {
              id: 'claude',
              kind: 'ai',
              provider: 'anthropic',
              label: 'Alternative',
            },
            {
              id: 'unsupported',
              kind: 'ai',
              provider: 'other',
              label: 'Unsupported',
            },
          ],
        }),
      )
    if (url.endsWith('/stream') && init?.method === 'POST')
      return new Response(
        'data: ' +
          JSON.stringify({
            type: 'complete',
            turn: {
              id: 'answer',
              request_id: 'request',
              mode: 'ask',
              text: 'Filter?',
              state: 'complete',
              result: {
                text: 'Synthetic Claude answer.',
                provider: 'anthropic',
                model: 'synthetic-claude',
                records: [{ id: 'car', name: 'Synthetic car', kind: 'asset' }],
              },
            },
          }) +
          '\n\n',
        { headers: { 'content-type': 'text/event-stream' } },
      )
    return original(url, init)
  })
  const openGraph = vi.fn()
  render(<ChatPanel csrfToken="csrf" onOpenGraph={openGraph} />)
  await screen.findByText('A place for the details')
  await user.selectOptions(screen.getByLabelText('Action'), 'ask')
  await user.selectOptions(screen.getByLabelText('AI connection'), 'openai')
  await user.type(screen.getByLabelText('Model ID'), 'old-model')
  await user.selectOptions(screen.getByLabelText('AI connection'), 'claude')
  expect(screen.getByLabelText('Model ID')).toHaveValue('')
  expect(screen.queryByRole('option', { name: /Unsupported/ })).toBeNull()
  await user.type(screen.getByLabelText('Model ID'), 'synthetic-claude')
  await user.type(screen.getByLabelText('Your question'), 'Filter?')
  await user.click(screen.getByRole('button', { name: 'Ask AI' }))
  await screen.findByText('Synthetic Claude answer.')
  expect(screen.getByText('Claude · synthetic-claude')).toBeVisible()
  await user.click(
    screen.getByRole('button', {
      name: 'Open Synthetic car in graph (record 1)',
    }),
  )
  expect(openGraph).toHaveBeenCalledWith('car')
  const posted = fetcher.mock.calls.find(
    ([url, init]) => url.endsWith('/stream') && init?.method === 'POST',
  )!
  expect(JSON.parse(String(posted[1]?.body))).toMatchObject({
    credential_id: 'claude',
    model: 'synthetic-claude',
    mode: 'ask',
  })
})

function mockServer() {
  const saved = {
    id: 'turn-1',
    request_id: 'r1',
    mode: 'save',
    text: 'My filter is 16x25x1.',
    state: 'complete',
    result: {
      text: 'Saved your original text as a memory.',
      sources: [{ id: 'source-1', text: 'My filter is 16x25x1.' }],
    },
  }
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/chat/preferences')
      return new Response(JSON.stringify({ credential_id: '', model: '' }))
    if (url === '/api/settings')
      return new Response(JSON.stringify({ allow_external_ai: false }))
    if (url.startsWith('/api/credentials'))
      return new Response(JSON.stringify({ items: [] }))
    if (url === '/api/chat/usage')
      return new Response(JSON.stringify({ requests: 0, limit: 20 }))
    if (url === '/api/chat/conversations' && init?.method === 'POST')
      return new Response(
        JSON.stringify({ id: 'chat-1', title: 'New conversation' }),
      )
    if (url === '/api/chat/conversations')
      return new Response(JSON.stringify({ items: [], next_cursor: null }))
    if (
      url === '/api/chat/conversations/chat-1/turns' &&
      init?.method === 'POST'
    )
      return new Response(JSON.stringify(saved))
    if (url === '/api/chat/conversations/chat-1/turns')
      return new Response(JSON.stringify({ items: [saved], next_cursor: null }))
    if (url.startsWith('/api/chat/sources/source-1'))
      return new Response(
        JSON.stringify({
          id: 'source-1',
          text: '<script>private evidence</script>',
          next_offset: null,
        }),
      )
    throw new Error('Unexpected request: ' + url)
  })
  vi.stubGlobal('fetch', fetcher)
  return fetcher
}

it('restores and explicitly saves a private model choice without enabling AI', async () => {
  const fetcher = mockServer()
  const original = fetcher.getMockImplementation()!
  let choice = { credential_id: 'claude', model: 'synthetic-old' }
  fetcher.mockImplementation(async (url, init) => {
    if (url.startsWith('/api/credentials'))
      return new Response(
        JSON.stringify({
          items: [
            {
              id: 'claude',
              kind: 'ai',
              provider: 'anthropic',
              label: 'Synthetic Claude',
            },
          ],
        }),
      )
    if (url === '/api/chat/preferences') {
      if (init?.method === 'PUT') {
        choice = JSON.parse(String(init.body))
        return new Response(null, { status: 204 })
      }
      return new Response(JSON.stringify(choice))
    }
    return original(url, init)
  })
  const mounted = render(<ChatPanel csrfToken="csrf" />)
  await userEvent.selectOptions(screen.getByLabelText('Action'), 'ask')
  await waitFor(() =>
    expect(screen.getByLabelText('Model ID')).toHaveValue('synthetic-old'),
  )
  await userEvent.clear(screen.getByLabelText('Model ID'))
  await userEvent.type(screen.getByLabelText('Model ID'), 'synthetic-new')
  await userEvent.click(
    screen.getByRole('button', { name: 'Remember AI choice' }),
  )
  expect(
    await screen.findByText('AI choice saved for your account.'),
  ).toBeVisible()
  expect(
    screen.getByText('Enable external AI access in Settings to continue.'),
  ).toBeVisible()
  mounted.unmount()
  render(<ChatPanel csrfToken="csrf" />)
  await userEvent.selectOptions(screen.getByLabelText('Action'), 'ask')
  await waitFor(() =>
    expect(screen.getByLabelText('Model ID')).toHaveValue('synthetic-new'),
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Forget saved AI choice' }),
  )
  await waitFor(() => expect(screen.getByLabelText('Model ID')).toHaveValue(''))
  expect(
    fetcher.mock.calls.some(
      ([url, init]) => url === '/api/settings' && init?.method === 'PUT',
    ),
  ).toBe(false)
})

describe('private text memory chat', () => {
  it('saves a note, opens evidence safely, and reloads persisted messages', async () => {
    const fetcher = mockServer()
    const user = userEvent.setup()
    render(<ChatPanel csrfToken="csrf" />)
    await screen.findByText('A place for the details')
    await user.type(
      screen.getByLabelText('Memory to save'),
      'My filter is 16x25x1.',
    )
    await user.click(screen.getByRole('button', { name: 'Save memory' }))
    await screen.findByText('Saved your original text as a memory.')
    const post = fetcher.mock.calls.find(
      ([url, init]) => url.endsWith('/turns') && init?.method === 'POST',
    )
    expect(JSON.parse(post![1]!.body as string)).toMatchObject({
      mode: 'save',
      text: 'My filter is 16x25x1.',
    })
    expect(post![1]!.headers).toMatchObject({ 'X-CSRF-Token': 'csrf' })
    await user.click(screen.getByRole('button', { name: /Source 1/ }))
    expect(
      await screen.findByText('<script>private evidence</script>'),
    ).toBeVisible()
    expect(document.querySelector('script')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'New conversation' }))
    await user.click(
      screen.getByRole('button', {
        name: 'My filter is 16x25x1.',
      }),
    )
    expect(
      await screen.findByText('Saved your original text as a memory.'),
    ).toBeVisible()
  })

  it('keeps keyword search independent of AI and explains unavailable AI access', async () => {
    mockServer()
    const user = userEvent.setup()
    render(<ChatPanel csrfToken="csrf" />)
    await screen.findByText('A place for the details')
    await user.selectOptions(screen.getByLabelText('Action'), 'search')
    expect(screen.getByLabelText('Search keywords')).toHaveAttribute(
      'maxlength',
      '200',
    )
    await user.type(screen.getByLabelText('Search keywords'), 'filter')
    expect(
      screen.getByRole('button', { name: 'Search memories' }),
    ).toBeEnabled()
    await user.selectOptions(screen.getByLabelText('Action'), 'ask')
    expect(
      screen.getByText('Enable external AI access in Settings to continue.'),
    ).toBeVisible()
    expect(screen.getByRole('button', { name: 'Ask AI' })).toBeDisabled()
  })

  it('retries a lost response using the same request ID', async () => {
    const fetcher = mockServer()
    const original = fetcher.getMockImplementation()!
    let lost = true
    fetcher.mockImplementation(async (url, init) => {
      if (url.endsWith('/turns') && init?.method === 'POST' && lost) {
        lost = false
        throw new Error('Network lost after save')
      }
      return original(url, init)
    })
    const user = userEvent.setup()
    render(<ChatPanel csrfToken="csrf" />)
    await screen.findByText('A place for the details')
    await user.type(
      screen.getByLabelText('Memory to save'),
      'My filter is 16x25x1.',
    )
    await user.click(screen.getByRole('button', { name: 'Save memory' }))
    await screen.findByRole('alert')
    await user.click(screen.getByRole('button', { name: 'Retry same request' }))
    await screen.findByText('Saved your original text as a memory.')
    const posts = fetcher.mock.calls.filter(
      ([url, init]) => url.endsWith('/turns') && init?.method === 'POST',
    )
    expect(posts).toHaveLength(2)
    expect(posts[0][1]!.body).toEqual(posts[1][1]!.body)
    await waitFor(() =>
      expect(screen.getByLabelText('Memory to save')).toBeEnabled(),
    )
  })
})

it('starts extraction only from a selected saved note and renders the persisted proposal', async () => {
  const fetcher = mockServer()
  const original = fetcher.getMockImplementation()!
  fetcher.mockImplementation(async (url, init) => {
    if (url === '/api/settings')
      return new Response(JSON.stringify({ allow_external_ai: true }))
    if (url.startsWith('/api/credentials'))
      return new Response(
        JSON.stringify({
          items: [
            {
              id: 'credential',
              kind: 'ai',
              provider: 'openai',
              label: 'Private OpenAI',
            },
          ],
        }),
      )
    if (url.startsWith('/api/chat/sources/'))
      return new Response(
        JSON.stringify({
          id: 'source-1',
          text: 'I own a trimmer.',
          next_offset: null,
          note: {
            is_current: true,
            can_correct: true,
            current_source_id: 'source-1',
            root_source_id: 'source-1',
          },
        }),
      )
    if (
      url.endsWith('/turns') &&
      init?.method === 'POST' &&
      JSON.parse(init.body as string).mode === 'extract'
    )
      return new Response(
        JSON.stringify({
          id: 'extract-turn',
          request_id: 'extract-key',
          mode: 'extract',
          state: 'complete',
          text: 'I own a trimmer.',
          result: {
            text: 'Review before adding inventory.',
            proposal_id: 'proposal',
          },
        }),
      )
    if (url === '/api/chat/asset-proposals/proposal')
      return new Response(
        JSON.stringify({
          id: 'proposal',
          source_id: 'source-1',
          current_source_id: 'source-1',
          stale: false,
          state: 'proposed',
          proposed: {
            candidate: {
              name: 'trimmer',
              manufacturer: null,
              model: null,
              serial: null,
              kind: 'possession',
              quote: 'I own a trimmer.',
            },
            explanation: 'A stated possession.',
          },
          reviewed: null,
          result: {},
        }),
      )
    return original(url, init)
  })
  const user = userEvent.setup()
  render(<ChatPanel csrfToken="csrf" />)
  await screen.findByText('A place for the details')
  await user.type(screen.getByLabelText('Memory to save'), 'I own a trimmer.')
  await user.click(screen.getByRole('button', { name: 'Save memory' }))
  await user.click(await screen.findByRole('button', { name: /Source 1/ }))
  await user.click(
    await screen.findByRole('button', {
      name: 'Suggest an asset from this note',
    }),
  )
  expect(screen.getByLabelText('Selected saved note')).toHaveValue(
    'I own a trimmer.',
  )
  expect(screen.getByLabelText('Selected saved note')).toHaveAttribute(
    'readonly',
  )
  await user.selectOptions(screen.getByLabelText('AI connection'), 'credential')
  await user.type(screen.getByLabelText('Model ID'), 'fixture-model')
  await user.click(screen.getByRole('button', { name: 'Suggest asset' }))
  expect(await screen.findByLabelText('Item name')).toHaveValue('trimmer')
  const posted = fetcher.mock.calls.find(
    ([url, init]) =>
      url.endsWith('/turns') &&
      init?.method === 'POST' &&
      JSON.parse(init.body as string).mode === 'extract',
  )!
  expect(JSON.parse(posted[1]!.body as string)).toMatchObject({
    mode: 'extract',
    source_id: 'source-1',
    text: 'I own a trimmer.',
    credential_id: 'credential',
  })
  expect(posted[1]!.headers).toMatchObject({ 'X-CSRF-Token': 'csrf' })
})

it('loads a selected memory as read-only receipt input and waits for explicit submission', async () => {
  const user = userEvent.setup()
  const fetcher = mockServer()
  const original = fetcher.getMockImplementation()!
  fetcher.mockImplementation(async (url, init) => {
    if (url === '/api/chat/sources/receipt-source')
      return new Response(
        JSON.stringify({
          id: 'receipt-source',
          text: 'Acme Drill Qty: 2',
          note: { is_current: true },
        }),
      )
    if (url === '/api/settings')
      return new Response(JSON.stringify({ allow_external_ai: true }))
    if (url.startsWith('/api/credentials'))
      return new Response(
        JSON.stringify({
          items: [
            { id: 'ai', kind: 'ai', provider: 'openai', label: 'Synthetic' },
          ],
        }),
      )
    if (url.endsWith('/turns') && init?.method === 'POST')
      return new Response(
        JSON.stringify({
          id: 'receipt-turn',
          mode: 'extract_receipt',
          text: 'Acme Drill Qty: 2',
          state: 'complete',
          result: { text: 'Ready for review', receipt_proposal_id: 'receipt' },
        }),
      )
    if (url === '/api/receipts/receipt')
      return new Response(
        JSON.stringify({
          id: 'receipt',
          source_id: 'receipt-source',
          current_source_id: 'receipt-source',
          stale: false,
          state: 'no_items',
          items: [],
          explanation: 'Synthetic test',
          result: {},
        }),
      )
    return original(url, init)
  })
  render(<ChatPanel csrfToken="csrf" initialReceiptSourceId="receipt-source" />)
  const input = await screen.findByLabelText('Selected saved note')
  await waitFor(() => expect(input).toHaveValue('Acme Drill Qty: 2'))
  expect(input).toHaveAttribute('readonly')
  expect(
    fetcher.mock.calls.some(
      ([url, init]) => url.endsWith('/turns') && init?.method === 'POST',
    ),
  ).toBe(false)
  await user.selectOptions(screen.getByLabelText('AI connection'), 'ai')
  await user.type(screen.getByLabelText('Model ID'), 'synthetic')
  await user.click(
    screen.getByRole('button', { name: 'Suggest receipt items' }),
  )
  await screen.findByText('Synthetic test')
  const [, init] = fetcher.mock.calls.find(
    ([url, init]) => url.endsWith('/turns') && init?.method === 'POST',
  )!
  expect(JSON.parse(String(init?.body))).toMatchObject({
    mode: 'extract_receipt',
    source_id: 'receipt-source',
    text: 'Acme Drill Qty: 2',
    credential_id: 'ai',
    model: 'synthetic',
  })
})
