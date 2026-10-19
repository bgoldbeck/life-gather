import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { MailboxesPanel } from './MailboxesPanel'

afterEach(() => vi.unstubAllGlobals())
const mailbox = {
  id: 'mailbox',
  address: 'synthetic@example.test',
  connected: true,
  revision: 1,
}

it('connects only on request with CSRF and a separate Google consent redirect', async () => {
  const user = userEvent.setup()
  const redirect = vi.fn()
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return new Response(
        JSON.stringify(
          url.endsWith('/start')
            ? {
                url: 'https://accounts.google.com/o/oauth2/v2/auth?state=synthetic',
              }
            : { items: [], oauth_configured: true, vault_configured: true },
        ),
      )
    }),
  )
  render(<MailboxesPanel csrfToken="csrf" onAuthorize={redirect} />)
  const connect = await screen.findByRole('button', { name: 'Connect Gmail' })
  expect(calls).toHaveLength(1)
  await user.click(connect)
  expect(redirect).toHaveBeenCalledWith(
    'https://accounts.google.com/o/oauth2/v2/auth?state=synthetic',
  )
  expect(calls[1].init?.headers).toMatchObject({ 'X-CSRF-Token': 'csrf' })
  expect(screen.getByText(/Connecting does not scan or send/)).toBeVisible()
})

it('disconnects one owned mailbox without exposing or asking for tokens', async () => {
  const user = userEvent.setup()
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return new Response(
        JSON.stringify(
          url.endsWith('/disconnect')
            ? { ...mailbox, connected: false, revision: 2 }
            : {
                items: [mailbox],
                oauth_configured: true,
                vault_configured: true,
              },
        ),
      )
    }),
  )
  render(<MailboxesPanel csrfToken="csrf" />)
  await user.click(
    await screen.findByRole('button', {
      name: 'Disconnect synthetic@example.test',
    }),
  )
  await screen.findByText('Disconnected')
  expect(JSON.parse(String(calls[1].init?.body))).toEqual({
    mailbox_id: 'mailbox',
    expected_revision: 1,
  })
  expect(screen.queryByLabelText(/secret|token/i)).not.toBeInTheDocument()
})

it('explains missing installation setup and disables connection', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            items: [],
            oauth_configured: false,
            vault_configured: false,
          }),
        ),
    ),
  )
  render(<MailboxesPanel csrfToken="csrf" />)
  expect(
    await screen.findByRole('button', { name: 'Connect Gmail' }),
  ).toBeDisabled()
  expect(screen.getByText(/installation owner/)).toBeVisible()
})
