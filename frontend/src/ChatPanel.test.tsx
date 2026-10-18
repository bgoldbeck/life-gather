import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ChatPanel } from './ChatPanel'

afterEach(() => vi.unstubAllGlobals())

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
    if (url.endsWith('/turns') && init?.method === 'POST')
      return new Response(
        JSON.stringify({
          id: 'answer',
          request_id: 'request',
          mode: 'ask',
          text: 'Filter?',
          state: 'complete',
          result: {
            text: 'Synthetic Claude answer.',
            provider: 'anthropic',
            model: 'synthetic-claude',
          },
        }),
      )
    return original(url, init)
  })
  render(<ChatPanel csrfToken="csrf" />)
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
  const posted = fetcher.mock.calls.find(
    ([url, init]) => url.endsWith('/turns') && init?.method === 'POST',
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
