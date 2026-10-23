import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthGate } from './AuthGate'

const anonymous = {
  configured: true,
  email_delivery_enabled: true,
  email_password_enabled: false,
  user: null,
  csrf_token: null,
}
const pending = {
  ...anonymous,
  user: { id: 'fixture', email: 'fixture@example.test', name: 'Fixture User' },
  csrf_token: 'fixture-csrf',
  terms: { version: '2026-10-23', accepted: false },
}
const reply = (body: unknown) => ({ ok: true, json: async () => body })

function gate() {
  return render(
    <AuthGate>{(user) => <p>Workspace for {user.name}</p>}</AuthGate>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  delete window.turnstile
})

describe('sign-up bot check', () => {
  it('needs a passed Turnstile check before sending a sign-up email', async () => {
    let solve: (token: string) => void = () => {}
    const turnstile = {
      render: vi.fn(
        (
          _: HTMLElement,
          options: { sitekey: string; callback: (token: string) => void },
        ) => {
          solve = options.callback
          return 'widget-1'
        },
      ),
      remove: vi.fn(),
    }
    window.turnstile = turnstile
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        reply({ ...anonymous, bot_check_site_key: '0x4AAAAAAAsynthetic' }),
      )
      .mockResolvedValue({ ok: true, status: 202 })
    vi.stubGlobal('fetch', fetch)
    gate()
    await userEvent.click(
      await screen.findByRole('button', { name: 'Create account' }),
    )
    await userEvent.type(screen.getByLabelText('Name'), 'Alice')
    await userEvent.type(screen.getByLabelText('Email'), 'alice@example.test')
    const send = screen.getByRole('button', { name: 'Send verification link' })
    expect(send).toBeDisabled()
    await waitFor(() => expect(turnstile.render).toHaveBeenCalled())
    expect(turnstile.render.mock.calls[0][1].sitekey).toBe(
      '0x4AAAAAAAsynthetic',
    )
    solve('passed-token')
    await waitFor(() => expect(send).toBeEnabled())
    await userEvent.click(send)
    expect(await screen.findByRole('status')).toHaveTextContent(
      'email will arrive',
    )
    expect(fetch).toHaveBeenLastCalledWith(
      '/auth/email/request/signup',
      expect.objectContaining({
        body: JSON.stringify({
          email: 'alice@example.test',
          name: 'Alice',
          bot_token: 'passed-token',
        }),
      }),
    )
    // Tokens are single-use: a fresh widget replaces the used one.
    await waitFor(() => expect(turnstile.render).toHaveBeenCalledTimes(2))
    expect(turnstile.remove).toHaveBeenCalledWith('widget-1')
    expect(
      screen.getByRole('button', { name: 'Send verification link' }),
    ).toBeDisabled()
  })

  it('shows no widget when the installation has no site key', async () => {
    const turnstile = { render: vi.fn(), remove: vi.fn() }
    window.turnstile = turnstile
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(anonymous)))
    gate()
    await userEvent.click(
      await screen.findByRole('button', { name: 'Create account' }),
    )
    expect(screen.queryByLabelText('Bot check')).not.toBeInTheDocument()
    expect(turnstile.render).not.toHaveBeenCalled()
  })
})

describe('terms of use', () => {
  it('keeps the workspace closed until the terms are accepted', async () => {
    const fetch = vi.fn(async (path: string) => {
      if (path === '/auth/terms')
        return reply({ version: '2026-10-23', text: 'Synthetic terms text' })
      if (path === '/auth/terms/accept') return { ok: true, status: 204 }
      return reply(
        fetch.mock.calls.some(([called]) => called === '/auth/terms/accept')
          ? { ...pending, terms: { version: '2026-10-23', accepted: true } }
          : pending,
      )
    })
    vi.stubGlobal('fetch', fetch)
    gate()
    expect(
      await screen.findByRole('region', { name: 'Terms of use text' }),
    ).toHaveTextContent('Synthetic terms text')
    expect(screen.queryByText(/Workspace for/)).not.toBeInTheDocument()
    const accept = screen.getByRole('button', { name: 'Accept and continue' })
    expect(accept).toBeDisabled()
    await userEvent.click(
      screen.getByRole('checkbox', { name: /agree to the terms of use/ }),
    )
    await userEvent.click(accept)
    expect(await screen.findByText('Workspace for Fixture User')).toBeVisible()
    expect(fetch).toHaveBeenCalledWith(
      '/auth/terms/accept',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ version: '2026-10-23' }),
        headers: expect.objectContaining({ 'X-CSRF-Token': 'fixture-csrf' }),
      }),
    )
  })

  it('lets someone who does not agree sign out instead', async () => {
    const fetch = vi.fn(async (path: string) => {
      if (path === '/auth/terms')
        return reply({ version: '2026-10-23', text: 'Synthetic terms text' })
      if (path === '/auth/logout') return { ok: true, status: 204 }
      return reply(pending)
    })
    vi.stubGlobal('fetch', fetch)
    gate()
    await screen.findByRole('region', { name: 'Terms of use text' })
    expect(screen.getByText('Don’t agree? Delete this account')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(
      await screen.findByRole('link', { name: 'Continue with Google' }),
    ).toBeVisible()
    expect(fetch).not.toHaveBeenCalledWith(
      '/auth/terms/accept',
      expect.anything(),
    )
  })
})
