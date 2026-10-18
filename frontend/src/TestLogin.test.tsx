import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'

const anonymous = {
  configured: false,
  test_login_enabled: true,
  user: null,
  csrf_token: null,
}
const reply = (body: unknown) => ({ ok: true, json: async () => body })
afterEach(() => vi.unstubAllGlobals())

it('offers one-click test login and keeps the banner after sign-in', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(reply(anonymous))
    .mockResolvedValueOnce({ ok: true, status: 204 })
    .mockResolvedValue(
      reply({
        ...anonymous,
        user: {
          id: 'test-id',
          name: 'Test user',
          email: 'test@lifegather.invalid',
        },
        csrf_token: 'test-csrf',
      }),
    )
  vi.stubGlobal('fetch', fetch)
  render(<App />)
  await userEvent.click(
    await screen.findByRole('button', { name: 'Continue as test user' }),
  )
  expect(fetch).toHaveBeenCalledWith(
    '/auth/test-login',
    expect.objectContaining({ method: 'POST', body: '{}' }),
  )
  expect(
    await screen.findByRole('button', { name: 'Sign out' }),
  ).toBeInTheDocument()
  expect(screen.getByText(/Test mode is enabled/)).toBeInTheDocument()
})

it('hides test login when the installation has not enabled it', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(reply({ ...anonymous, test_login_enabled: false })),
  )
  render(<App />)
  await screen.findByRole('button', { name: 'Sign in' })
  expect(
    screen.queryByRole('button', { name: 'Continue as test user' }),
  ).not.toBeInTheDocument()
  expect(screen.queryByText(/Test mode is enabled/)).not.toBeInTheDocument()
})

it('shows a retryable error when test login fails', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValueOnce(reply(anonymous))
      .mockResolvedValue({ ok: false }),
  )
  render(<App />)
  await userEvent.click(
    await screen.findByRole('button', { name: 'Continue as test user' }),
  )
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Unable to enter the test workspace',
  )
  expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled()
})
