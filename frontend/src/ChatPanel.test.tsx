import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ChatPanel } from './ChatPanel'

afterEach(() => vi.unstubAllGlobals())

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
    expect(screen.getByRole('button', { name: 'Ask OpenAI' })).toBeDisabled()
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
