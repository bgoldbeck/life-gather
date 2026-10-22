import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ChatPanel } from './ChatPanel'

afterEach(() => vi.unstubAllGlobals())

const turn = {
  id: 'turn-1',
  request_id: 'r1',
  mode: 'assistant',
  text: 'Save the serial from this manual to my drill.',
  state: 'complete',
  result: {
    text: 'Saved serial (SN-77821) for Drill. Serial came from the attached document drill-manual.txt, saved as its evidence.',
    sources: [{ id: 'doc-source', text: '[L1] Serial: SN-77821' }],
  },
}

function mockServer() {
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
              label: 'Synthetic',
            },
          ],
        }),
      )
    if (url === '/api/chat/usage')
      return new Response(JSON.stringify({ requests: 0, limit: 20 }))
    if (url.startsWith('/api/documents'))
      return new Response(
        JSON.stringify({
          items: [{ id: 'doc-1', filename: 'drill-manual.txt', format: 'txt' }],
          next_cursor: null,
        }),
      )
    if (url === '/api/chat/conversations' && init?.method === 'POST')
      return new Response(
        JSON.stringify({ id: 'chat-1', title: 'New conversation' }),
      )
    if (url === '/api/chat/conversations')
      return new Response(JSON.stringify({ items: [], next_cursor: null }))
    if (url === '/api/chat/conversations/chat-1/stream')
      return new Response(
        `data: ${JSON.stringify({ type: 'complete', turn })}\n\n`,
        { headers: { 'content-type': 'text/event-stream' } },
      )
    throw new Error('Unexpected request: ' + url)
  })
  vi.stubGlobal('fetch', fetcher)
  return fetcher
}

function streamBodies(fetcher: ReturnType<typeof mockServer>) {
  return fetcher.mock.calls
    .filter(([url]) => url === '/api/chat/conversations/chat-1/stream')
    .map(([, init]) => JSON.parse(String(init?.body)))
}

it('attaches one saved document to an AI assistant message', async () => {
  const fetcher = mockServer()
  render(<ChatPanel csrfToken="csrf" />)
  await screen.findByText('A place for the details')
  await userEvent.selectOptions(screen.getByLabelText('Action'), 'assistant')
  await userEvent.click(
    screen.getByRole('button', { name: 'Attach a document' }),
  )
  // Choosing makes no AI request.
  await userEvent.click(
    screen.getByRole('button', { name: 'Load saved documents' }),
  )
  await userEvent.click(
    await screen.findByRole('button', {
      name: 'Attach document drill-manual.txt',
    }),
  )
  expect(screen.getByText('drill-manual.txt')).toBeVisible()
  expect(streamBodies(fetcher)).toEqual([])
  await userEvent.type(
    screen.getByLabelText('Message your assistant'),
    'Save the serial from this manual to my drill.',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Send' }))
  expect(
    await screen.findByText(/came from the attached document/),
  ).toBeVisible()
  expect(streamBodies(fetcher)[0]).toMatchObject({
    mode: 'assistant',
    document_id: 'doc-1',
  })
  expect(streamBodies(fetcher)[0]).not.toHaveProperty('photo_id')
  // The attachment is cleared after the reply; a later message sends none.
  expect(
    screen.getByRole('button', { name: 'Attach a document' }),
  ).toBeVisible()
})

it('can remove an attachment before sending', async () => {
  const fetcher = mockServer()
  render(<ChatPanel csrfToken="csrf" />)
  await screen.findByText('A place for the details')
  await userEvent.selectOptions(screen.getByLabelText('Action'), 'assistant')
  await userEvent.click(
    screen.getByRole('button', { name: 'Attach a document' }),
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Load saved documents' }),
  )
  await userEvent.click(
    await screen.findByRole('button', {
      name: 'Attach document drill-manual.txt',
    }),
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Remove attachment' }),
  )
  await userEvent.type(
    screen.getByLabelText('Message your assistant'),
    'What color is my bicycle?',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Send' }))
  await screen.findByText(/came from the attached document/)
  expect(streamBodies(fetcher)[0]).not.toHaveProperty('document_id')
})
