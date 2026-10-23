import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ScansPanel } from './ScansPanel'

afterEach(() => vi.unstubAllGlobals())

it('opens the exact saved Chat job without starting another scan', async () => {
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    expect(init?.method ?? 'GET').toBe('GET')
    return new Response(
      JSON.stringify(
        url.includes('/scans/chat-run')
          ? {
              id: 'chat-run',
              state: 'completed',
              handler_key: 'gmail_import',
              items: [
                {
                  sequence: 1,
                  label: 'Synthetic saved Chat evidence',
                  state: 'saved',
                  reason: '',
                },
              ],
              next_after: null,
            }
          : { items: [] },
      ),
    )
  })
  vi.stubGlobal('fetch', fetcher)
  render(<ScansPanel csrfToken="csrf" initialRunId="chat-run" />)
  expect(
    await screen.findByRole('region', { name: 'Scan results' }),
  ).toHaveTextContent('Synthetic saved Chat evidence')
  await waitFor(() =>
    expect(screen.getByRole('region', { name: 'Scan results' })).toHaveFocus(),
  )
  expect(
    fetcher.mock.calls.some(([url]) => url.startsWith('/api/scans/chat-run')),
  ).toBe(true)
})

it('explicitly selects purchase discovery and its private AI connection', async () => {
  const user = userEvent.setup()
  let saved: Record<string, unknown> | null = null
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        saved = JSON.parse(String(init.body))
        return new Response(
          JSON.stringify({ id: 'discovered', state: 'completed' }),
        )
      }
      const value = url.includes('mailboxes')
        ? {
            items: [
              {
                id: 'mailbox',
                address: 'synthetic@example.test',
                connected: true,
              },
            ],
          }
        : url.includes('credentials')
          ? {
              items: [
                {
                  id: 'ai',
                  kind: 'ai',
                  provider: 'openai',
                  label: 'Synthetic AI',
                },
              ],
            }
          : url.endsWith('settings')
            ? { allow_external_ai: true }
            : url.includes('/scans/discovered')
              ? {
                  id: 'discovered',
                  state: 'completed',
                  handler_key: 'gmail_discovery',
                  items: [
                    {
                      sequence: 1,
                      source_id: null,
                      label: 'Receipt',
                      state: 'saved',
                      reason: '',
                      metadata: { created: 1, enriched: 0, review: 1 },
                    },
                  ],
                }
              : { items: [] }
      return new Response(JSON.stringify(value))
    }),
  )
  const navigate = vi.fn()
  render(<ScansPanel csrfToken="csrf" onNavigate={navigate} />)
  await screen.findAllByText('synthetic@example.test')
  await user.click(screen.getByLabelText('Discover purchases with AI'))
  await screen.findByRole('option', { name: 'Synthetic AI (openai)' })
  await user.selectOptions(
    screen.getByLabelText('Discovery AI connection'),
    'ai',
  )
  await user.type(screen.getByLabelText('Discovery model'), 'synthetic-model')
  await user.click(screen.getByRole('button', { name: /^Start email scan$/ }))
  await screen.findByText(/1 created · 0 enriched · 1 need review/)
  expect(saved).toMatchObject({
    handler_key: 'gmail_discovery',
    config: { credential_id: 'ai', model: 'synthetic-model' },
  })
  await user.click(
    screen.getByRole('button', { name: 'Review uncertain matches' }),
  )
  expect(navigate).toHaveBeenCalledWith('Review')
})

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
  await screen.findAllByText('synthetic@example.test')
  expect(writes).toHaveLength(0)
  await user.click(screen.getByRole('button', { name: /^Start email scan$/ }))
  await screen.findByRole('alert')
  await user.click(screen.getByRole('button', { name: /^Retry scan request$/ }))
  await waitFor(() => expect(writes).toHaveLength(2))
  expect(writes[0].body).toEqual(writes[1].body)
  expect(writes[0].headers).toMatchObject({ 'X-CSRF-Token': 'csrf' })
})

it('imports attached documents without AI and links to Documents', async () => {
  const user = userEvent.setup()
  let saved: Record<string, unknown> | null = null
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        saved = JSON.parse(String(init.body))
        return new Response(JSON.stringify({ id: 'files', state: 'completed' }))
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
            : url.includes('/scans/files')
              ? {
                  id: 'files',
                  state: 'completed',
                  handler_key: 'gmail_attachments',
                  items: [
                    {
                      sequence: 1,
                      source_id: null,
                      label: 'Synthetic order',
                      state: 'saved',
                      reason: '',
                      metadata: {
                        attachments_saved: 2,
                        photos_saved: 1,
                        attachments_skipped: 2,
                      },
                    },
                  ],
                  next_after: null,
                }
              : { items: [] },
        ),
      )
    }),
  )
  const navigate = vi.fn()
  render(<ScansPanel csrfToken="csrf" onNavigate={navigate} />)
  await screen.findAllByText('synthetic@example.test')
  await user.click(screen.getByLabelText('Discover purchases with AI'))
  await user.click(
    screen.getByLabelText('Import attached documents and photos for review'),
  )
  expect(screen.getByLabelText('Discover purchases with AI')).toBeDisabled()
  expect(screen.queryByLabelText('Discovery model')).toBeNull()
  await user.click(screen.getByRole('button', { name: /^Start email scan$/ }))
  await screen.findByText(/2 attachments saved \(1 photo\) · 2 not imported/)
  expect(saved).toMatchObject({
    handler_key: 'gmail_attachments',
    config: { max_messages: 10 },
  })
  expect(JSON.stringify(saved)).not.toContain('credential_id')
  await user.click(
    screen.getByRole('button', { name: 'Review imported documents' }),
  )
  expect(navigate).toHaveBeenCalledWith('Documents')
  await user.click(
    screen.getByRole('button', { name: 'Review imported photos' }),
  )
  expect(navigate).toHaveBeenCalledWith('Photos')
})
