import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ChatPanel } from './ChatPanel'
import { MailboxesPanel } from './MailboxesPanel'
import { PowerCenter, type PowerSnapshot } from './PowerCenter'
import { PrivateSettingsPanel } from './PrivateSettingsPanel'
import { ReconnectButton } from './ReconnectButton'

const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status })
const now = Math.floor(Date.now() / 1000)
const consent = 'https://accounts.google.com/o/oauth2/v2/auth?state=synthetic'

beforeEach(() => sessionStorage.clear())
afterEach(() => vi.unstubAllGlobals())

function power(): PowerSnapshot {
  const source = {
    configured: true,
    state: 'failed' as const,
    capabilities: [],
    action: 'Settings' as const,
    last_success: null,
    freshness: 'unknown',
    scope: '',
  }
  return {
    checked_at: now,
    expires_at: now + 300,
    scoring_version: '1',
    score: 55,
    minimum_score: 55,
    maximum_score: 55,
    capabilities: [],
    sources: [
      {
        ...source,
        id: 'openai',
        title: 'OpenAI',
        category: 'ai',
        reason: 'OpenAI refused the saved key “Work key”.',
        reconnect: { kind: 'ai', provider: 'openai' },
      },
      {
        ...source,
        id: 'mailbox-1',
        title: 'owner@example.test',
        category: 'email',
        reason: 'Gmail access expired or was revoked.',
        reconnect: {
          kind: 'gmail',
          provider: 'gmail',
          mailbox_id: 'mailbox-1',
        },
      },
    ],
    issues: [
      {
        id: 'mailbox-1',
        title: 'owner@example.test',
        reason: 'Gmail access expired or was revoked.',
        action: 'Settings',
        state: 'failed',
        run_id: null,
        reconnect: {
          kind: 'gmail',
          provider: 'gmail',
          mailbox_id: 'mailbox-1',
        },
      },
    ],
    issues_truncated: false,
    connected_sources: 2,
    completed_scans_7d: 0,
    imported_messages_7d: 0,
    period_start: now - 7 * 86400,
    ai_requests: 1,
    ai_limit: 20,
    ai_resets_at: now + 86400,
    paused_schedules: 0,
  }
}

it('offers Reconnect for refused Gmail and AI sign-ins in Power Center', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => json(power())),
  )
  const reconnect = vi.fn()
  render(
    <PowerCenter
      userId="alice"
      csrfToken="csrf"
      onNavigate={vi.fn()}
      onReconnectKey={reconnect}
    />,
  )
  await userEvent.click(
    await screen.findByRole('button', { name: 'Reconnect OpenAI' }),
  )
  expect(reconnect).toHaveBeenCalledWith({ kind: 'ai', provider: 'openai' })
  // The mailbox card and its health issue both offer Gmail consent.
  expect(
    screen.getAllByRole('button', { name: 'Reconnect Gmail' }),
  ).toHaveLength(2)
})

it('starts Google consent in one click for a refused Gmail grant', async () => {
  const fetcher = vi.fn(async () => json({ url: consent }))
  vi.stubGlobal('fetch', fetcher)
  const authorize = vi.fn()
  render(
    <ReconnectButton
      target={{ kind: 'gmail', provider: 'gmail', mailbox_id: 'mailbox-1' }}
      csrfToken="csrf"
      onAuthorize={authorize}
    />,
  )
  await userEvent.click(screen.getByRole('button', { name: 'Reconnect Gmail' }))
  expect(authorize).toHaveBeenCalledWith(consent)
  const [path, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit]
  expect(path).toBe('/api/mailboxes/google/start')
  expect(new Headers(init.headers).get('X-CSRF-Token')).toBe('csrf')
})

it('refuses a consent redirect that is not Google', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => json({ url: 'https://example.test/phish' })),
  )
  const authorize = vi.fn()
  render(
    <ReconnectButton
      target={{ kind: 'gmail', provider: 'gmail' }}
      csrfToken="csrf"
      onAuthorize={authorize}
    />,
  )
  await userEvent.click(screen.getByRole('button', { name: 'Reconnect Gmail' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Unable to start Gmail consent',
  )
  expect(authorize).not.toHaveBeenCalled()
})

it('marks an expired mailbox and reconnects it from Settings', async () => {
  const fetcher = vi.fn(async (path: string) =>
    path === '/api/mailboxes'
      ? json({
          items: [
            {
              id: 'mailbox-1',
              address: 'owner@example.test',
              connected: true,
              needs_reconnect: true,
              revision: 2,
            },
          ],
          oauth_configured: true,
          vault_configured: true,
        })
      : json({ url: consent }),
  )
  vi.stubGlobal('fetch', fetcher)
  const authorize = vi.fn()
  render(<MailboxesPanel csrfToken="csrf" onAuthorize={authorize} />)
  expect(await screen.findByText(/Access expired or was revoked/)).toBeVisible()
  await userEvent.click(
    screen.getByRole('button', { name: 'Reconnect owner@example.test' }),
  )
  expect(authorize).toHaveBeenCalledWith(consent)
})

it('opens the Replace form for the refused AI key', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string) =>
      path === '/api/settings'
        ? json({ allow_external_ai: true, vault_configured: true })
        : json({
            items: [
              { id: 'ok', kind: 'ai', provider: 'openai', label: 'Home key' },
              {
                id: 'refused',
                kind: 'ai',
                provider: 'openai',
                label: 'Work key',
                auth_state: 'reconnect',
              },
            ],
            next_cursor: null,
          }),
    ),
  )
  render(
    <PrivateSettingsPanel
      csrfToken="csrf"
      reconnect={{ kind: 'ai', provider: 'openai' }}
    />,
  )
  expect(
    await screen.findByText('Replace credential: Work key'),
  ).toBeInTheDocument()
  expect(screen.getByText(/Paste a new key for “Work key”/)).toBeVisible()
  expect(
    screen.getByText('Refused by the provider; expired or revoked'),
  ).toBeVisible()
  expect(
    screen.getByRole('button', { name: 'Reconnect Work key' }),
  ).toBeVisible()
})

it('shows Reconnect on a chat reply whose AI key was refused', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, init?: RequestInit) => {
      if (path === '/api/settings') return json({ allow_external_ai: true })
      if (path === '/api/credentials?limit=100')
        return json({
          items: [
            {
              id: 'credential',
              kind: 'ai',
              provider: 'openai',
              label: 'Work key',
            },
          ],
        })
      if (path === '/api/chat/preferences')
        return json({ credential_id: 'credential', model: 'synthetic-model' })
      if (path === '/api/chat/usage') return json({ requests: 0 })
      if (path === '/api/chat/conversations' && init?.method === 'POST')
        return json({ id: 'new', title: 'New conversation' })
      if (path === '/api/chat/conversations')
        return json({ items: [], next_cursor: null })
      if (path.includes('/stream') || path.includes('/turns')) {
        if (init?.method !== 'POST')
          return json({ items: [], next_cursor: null })
        const body = JSON.parse(String(init.body))
        return json({
          id: 'turn-1',
          request_id: body.request_id,
          mode: body.mode,
          text: body.text,
          state: 'failed',
          result: {
            text: 'The AI provider refused the saved key. Reconnect it.',
            reconnect: {
              kind: 'ai',
              credential_id: 'credential',
              provider: 'openai',
            },
          },
        })
      }
      throw new Error('Unexpected synthetic request: ' + path)
    }),
  )
  const reconnect = vi.fn()
  render(<ChatPanel csrfToken="csrf" onReconnectKey={reconnect} />)
  const user = userEvent.setup()
  await user.selectOptions(await screen.findByLabelText('Action'), 'research')
  await user.type(screen.getByLabelText('What to look up'), 'DW-100 manual')
  await user.click(screen.getByRole('button', { name: 'Research on the web' }))
  await user.click(
    await screen.findByRole('button', { name: 'Reconnect OpenAI' }),
  )
  expect(reconnect).toHaveBeenCalledWith({
    kind: 'ai',
    credential_id: 'credential',
    provider: 'openai',
  })
})
