import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const anonymous = { configured: true, user: null, csrf_token: null }
const authenticated = {
  configured: true,
  user: { id: 'fixture', email: 'fixture@example.test', name: 'Fixture User' },
  csrf_token: 'fixture-csrf',
}
const reply = (body: unknown) => ({ ok: true, json: async () => body })

afterEach(() => vi.unstubAllGlobals())

describe('Google sign-in', () => {
  it('offers sign-in without rendering the private workspace', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(anonymous)))
    render(<App />)
    expect(
      await screen.findByRole('link', { name: 'Continue with Google' }),
    ).toHaveAttribute('href', '/auth/google/start')
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
  })

  it('explains missing server configuration', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(reply({ ...anonymous, configured: false })),
    )
    render(<App />)
    expect(await screen.findByText(/needs to be configured/)).toBeVisible()
    expect(
      screen.queryByRole('link', { name: 'Continue with Google' }),
    ).not.toBeInTheDocument()
  })

  it('shows loading and lets a failed connection be retried', async () => {
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue(reply(anonymous))
    vi.stubGlobal('fetch', fetch)
    render(<App />)
    expect(screen.getByRole('status')).toHaveTextContent(
      'Checking your session',
    )
    await screen.findByRole('alert')
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(
      await screen.findByRole('link', { name: 'Continue with Google' }),
    ).toBeVisible()
  })

  it('shows the signed-in account and logs out with CSRF protection', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(reply(authenticated))
      .mockResolvedValue({ ok: true, status: 204 })
    vi.stubGlobal('fetch', fetch)
    render(<App />)
    expect(await screen.findByText('Fixture User')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(
      await screen.findByRole('link', { name: 'Continue with Google' }),
    ).toBeVisible()
    expect(fetch).toHaveBeenLastCalledWith(
      '/auth/logout',
      expect.objectContaining({
        method: 'POST',
        headers: { 'X-CSRF-Token': 'fixture-csrf' },
      }),
    )
  })

  it('clears the workspace when a session has expired', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(reply(authenticated))
      .mockResolvedValue(reply(anonymous))
    vi.stubGlobal('fetch', fetch)
    render(<App />)
    await screen.findByText('Fixture User')
    await act(async () => window.dispatchEvent(new Event('focus')))
    await waitFor(() =>
      expect(screen.queryByRole('navigation')).not.toBeInTheDocument(),
    )
    expect(
      await screen.findByRole('link', { name: 'Continue with Google' }),
    ).toBeVisible()
  })
})
