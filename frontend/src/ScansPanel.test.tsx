import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ScansPanel } from './ScansPanel'

afterEach(() => vi.unstubAllGlobals())

it('requires an explicit request and reuses its identity after an uncertain response', async () => {
  const user = userEvent.setup()
  const writes: RequestInit[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        writes.push(init)
        if (writes.length === 1) throw new Error('Lost response')
        return new Response(
          JSON.stringify({
            id: 'run',
            state: 'completed',
            scanned: 0,
            imported: 0,
            existing: 0,
            skipped: 0,
            handler_key: 'gmail_import',
            created_at: 100,
          }),
        )
      }
      return new Response(
        JSON.stringify(
          url.includes('mailboxes')
            ? {
                items: [
                  {
                    id: 'mailbox',
                    address: 'synthetic@example.test',
                    connected: true,
                  },
                ],
              }
            : url.endsWith('/run')
              ? { id: 'run', state: 'completed', items: [] }
              : { items: [] },
        ),
      )
    }),
  )
  render(<ScansPanel csrfToken="csrf" />)
  await screen.findByText('synthetic@example.test')
  expect(writes).toHaveLength(0)
  await user.click(screen.getByRole('button', { name: /^Start email scan$/ }))
  await screen.findByRole('alert')
  await user.click(screen.getByRole('button', { name: /^Retry scan request$/ }))
  await waitFor(() => expect(writes).toHaveLength(2))
  expect(writes[0].body).toEqual(writes[1].body)
  expect(writes[0].headers).toMatchObject({ 'X-CSRF-Token': 'csrf' })
})
