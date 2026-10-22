import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ChatPanel } from './ChatPanel'

afterEach(() => vi.unstubAllGlobals())

const json = (value: unknown) => new Response(JSON.stringify(value))
const stream = (turn: unknown) =>
  new Response(`data: ${JSON.stringify({ type: 'complete', turn })}\n\n`, {
    headers: { 'content-type': 'text/event-stream' },
  })

it('shows the assistant scan receipt and opens the queued scan', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/chat/preferences')
        return json({ credential_id: 'openai', model: 'synthetic-model' })
      if (url === '/api/settings') return json({ allow_external_ai: true })
      if (url.startsWith('/api/credentials'))
        return json({
          items: [
            {
              id: 'openai',
              kind: 'ai',
              provider: 'openai',
              label: 'Synthetic OpenAI',
            },
          ],
        })
      if (url === '/api/chat/usage') return json({ requests: 0, limit: 20 })
      if (url === '/api/chat/conversations' && init?.method === 'POST')
        return json({ id: 'chat-1', title: 'New conversation' })
      if (url === '/api/chat/conversations')
        return json({ items: [], next_cursor: null })
      if (url === '/api/chat/conversations/chat-1/stream')
        return stream({
          id: 'turn-1',
          request_id: 'r1',
          mode: 'assistant',
          text: 'Find purchases in my Gmail from last week.',
          state: 'complete',
          result: {
            text: 'Started a purchase discovery scan of synthetic@example.test.',
            provider: 'openai',
            model: 'synthetic-model',
            scan_run_id: 'run-1',
          },
        })
      throw new Error('Unexpected request: ' + url)
    }),
  )
  const opened = vi.fn()
  render(<ChatPanel csrfToken="csrf" onOpenScan={opened} />)
  await screen.findByText('A place for the details')
  await userEvent.selectOptions(screen.getByLabelText('Action'), 'assistant')
  expect(screen.getByText(/find purchases in my Gmail/)).toBeVisible()
  await userEvent.type(
    screen.getByLabelText('Message your assistant'),
    'Find purchases in my Gmail from last week.',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Send' }))
  expect(
    await screen.findByText(
      'Started a purchase discovery scan of synthetic@example.test.',
    ),
  ).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'View email scan' }))
  expect(opened).toHaveBeenCalledWith('run-1')
})
