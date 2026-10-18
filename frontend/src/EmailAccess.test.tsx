import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const anonymous = {
  configured: true,
  email_delivery_enabled: true,
  email_password_enabled: false,
  user: null,
  csrf_token: null,
}
const reply = (body: unknown) => ({ ok: true, json: async () => body })

afterEach(() => {
  vi.unstubAllGlobals()
  window.history.replaceState(null, '', '/')
})

describe('email authentication', () => {
  it('requests verification before choosing a password', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(reply(anonymous))
      .mockResolvedValue({ ok: true, status: 202 })
    vi.stubGlobal('fetch', fetch)
    render(<App />)
    await userEvent.click(
      await screen.findByRole('button', { name: 'Create account' }),
    )
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Name'), 'Alice')
    await userEvent.type(screen.getByLabelText('Email'), 'alice@example.test')
    await userEvent.click(
      screen.getByRole('button', { name: 'Send verification link' }),
    )
    expect(await screen.findByRole('status')).toHaveTextContent(
      'email will arrive',
    )
    expect(fetch).toHaveBeenLastCalledWith(
      '/auth/email/request/signup',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ email: 'alice@example.test', name: 'Alice' }),
      }),
    )
  })

  it('offers password recovery and keeps missing mail configuration honest', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          reply({ ...anonymous, email_delivery_enabled: false }),
        ),
    )
    render(<App />)
    expect(
      await screen.findByRole('button', { name: 'Forgot password?' }),
    ).toBeDisabled()
    expect(
      screen.getByRole('button', { name: 'Create account' }),
    ).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled()
  })

  it('clears passwords after a failed sign-in without persisting them', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(reply(anonymous))
      .mockResolvedValue({
        ok: false,
        json: async () => ({ detail: 'Email or password is incorrect' }),
      })
    vi.stubGlobal('fetch', fetch)
    render(<App />)
    await userEvent.type(
      await screen.findByLabelText('Email'),
      'alice@example.test',
    )
    await userEvent.type(
      screen.getByLabelText('Password'),
      'a long password example 42',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('incorrect')
    expect(screen.getByLabelText('Password')).toHaveValue('')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('removes reset tokens from the URL and waits for explicit completion', async () => {
    window.history.replaceState(
      null,
      '',
      '/#auth=reset&token=fixture-token-with-enough-entropy',
    )
    const fetch = vi.fn().mockResolvedValue(reply(anonymous))
    vi.stubGlobal('fetch', fetch)
    render(<App />)
    await screen.findByLabelText('New password')
    expect(window.location.hash).toBe('')
    expect(fetch).toHaveBeenCalledTimes(1)
    await userEvent.type(
      screen.getByLabelText('New password'),
      'a brand new passphrase 42',
    )
    await userEvent.type(
      screen.getByLabelText('Confirm password'),
      'a brand new passphrase 42',
    )
    fetch.mockImplementation(async (path: string) =>
      path === '/auth/session' ? reply(anonymous) : { ok: true, status: 204 },
    )
    await userEvent.click(screen.getByRole('button', { name: 'Save password' }))
    expect(
      await screen.findByText('Your password is saved. Sign in to continue.'),
    ).toBeVisible()
    expect(fetch).toHaveBeenCalledWith(
      '/auth/email/complete',
      expect.objectContaining({
        body: JSON.stringify({
          purpose: 'reset',
          token: 'fixture-token-with-enough-entropy',
          password: 'a brand new passphrase 42',
        }),
      }),
    )
  })

  it('displays expired-link errors and clears the new password fields', async () => {
    window.history.replaceState(
      null,
      '',
      '/#auth=signup&token=fixture-token-with-enough-entropy',
    )
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(reply(anonymous))
      .mockResolvedValue({
        ok: false,
        json: async () => ({ detail: 'This link is invalid or expired' }),
      })
    vi.stubGlobal('fetch', fetch)
    render(<App />)
    await userEvent.type(
      await screen.findByLabelText('New password'),
      'a long signup password 42',
    )
    await userEvent.type(
      screen.getByLabelText('Confirm password'),
      'a long signup password 42',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Save password' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('expired')
    expect(screen.getByLabelText('New password')).toHaveValue('')
    expect(screen.getByLabelText('Confirm password')).toHaveValue('')
  })

  it('requests setup for the signed-in workspace with CSRF', async () => {
    const user = {
      id: 'google-user',
      name: 'Alice',
      email: 'alice@example.test',
    }
    const fetch = vi.fn().mockImplementation(async (path: string) => {
      if (path === '/auth/session')
        return reply({ ...anonymous, user, csrf_token: 'csrf' })
      if (path === '/api/settings')
        return reply({ allow_external_ai: false, vault_configured: false })
      if (path === '/api/credentials')
        return reply({ items: [], next_cursor: null })
      return { ok: true, status: 202 }
    })
    vi.stubGlobal('fetch', fetch)
    render(<App />)
    await userEvent.click(
      await screen.findByRole('button', { name: 'Settings' }),
    )
    await userEvent.click(
      screen.getByRole('button', { name: 'Set up password' }),
    )
    await waitFor(() =>
      expect(screen.getByText(/Open it in this browser/)).toBeVisible(),
    )
    expect(fetch).toHaveBeenCalledWith(
      '/auth/email/setup',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'csrf' },
      }),
    )
  })
})
