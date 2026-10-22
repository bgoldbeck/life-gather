import { render, screen, waitFor, act, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => {
  vi.unstubAllGlobals()
  document.documentElement.classList.remove('dark', 'forest')
})

it('follows device changes when System is selected', async () => {
  let changed = () => {}
  const media = {
    matches: false,
    addEventListener: (_event: string, callback: () => void) => {
      changed = callback
    },
    removeEventListener: vi.fn(),
  }
  vi.stubGlobal('matchMedia', () => media)
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ configured: false, user: null, csrf_token: null }),
    }),
  )
  render(<App />)
  await screen.findByRole('button', { name: 'Sign in' })
  expect(document.documentElement).not.toHaveClass('dark')
  media.matches = true
  await act(async () => changed())
  expect(document.documentElement).toHaveClass('dark')
})

it('keeps the saved theme when a save fails', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === 'PUT') return { ok: false }
      return {
        ok: true,
        json: async () =>
          path === '/auth/session'
            ? {
                configured: false,
                user: { id: 'alice', name: 'Alice', email: 'a@example.test' },
                csrf_token: 'csrf',
                appearance: 'light',
              }
            : path === '/api/settings'
              ? { allow_external_ai: false, vault_configured: false }
              : { items: [], next_cursor: null },
      }
    }),
  )
  render(<App />)
  await screen.findByText('Alice')
  await userEvent.click(screen.getByRole('button', { name: 'Settings' }))
  await userEvent.selectOptions(screen.getByLabelText('Color theme'), 'dark')
  await userEvent.click(screen.getByRole('button', { name: 'Save appearance' }))
  expect(
    await within(screen.getByRole('region', { name: 'Appearance' })).findByRole(
      'alert',
    ),
  ).toHaveTextContent('Unable to save appearance')
  expect(document.documentElement).not.toHaveClass('dark')
})

it('saves the private appearance and applies it throughout the app', async () => {
  let appearance = 'dark'
  const fetch = vi.fn(async (path: string, init?: RequestInit) => {
    if (path === '/api/appearance' && init?.method === 'PUT') {
      appearance = JSON.parse(init.body as string).theme
      return { ok: true, status: 204 }
    }
    const body =
      path === '/auth/session'
        ? {
            configured: false,
            user: { id: 'alice', name: 'Alice', email: 'a@example.test' },
            csrf_token: 'csrf',
            appearance,
          }
        : path === '/api/settings'
          ? { allow_external_ai: false, vault_configured: false }
          : { items: [], next_cursor: null }
    return { ok: true, json: async () => body }
  })
  vi.stubGlobal('fetch', fetch)
  render(<App />)
  await screen.findByText('Alice')
  await waitFor(() => expect(document.documentElement).toHaveClass('dark'))
  await userEvent.click(screen.getByRole('button', { name: 'Settings' }))
  await userEvent.selectOptions(screen.getByLabelText('Color theme'), 'light')
  await userEvent.click(screen.getByRole('button', { name: 'Save appearance' }))
  await waitFor(() => expect(document.documentElement).not.toHaveClass('dark'))
  expect(fetch).toHaveBeenCalledWith(
    '/api/appearance',
    expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ theme: 'light' }),
      headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf' }),
    }),
  )
})

it('clears a user theme after sign-out and when another account is loaded', async () => {
  let account = { id: 'alice', name: 'Alice', email: 'a@example.test' }
  let appearance = 'dark'
  let signed = true
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string) => {
      if (path === '/auth/logout') {
        signed = false
        return { ok: true, status: 204 }
      }
      return {
        ok: true,
        json: async () => ({
          configured: false,
          user: signed ? account : null,
          csrf_token: signed ? 'csrf' : null,
          appearance,
        }),
      }
    }),
  )
  render(<App />)
  await screen.findByText('Alice')
  await waitFor(() => expect(document.documentElement).toHaveClass('dark'))
  account = { id: 'bob', name: 'Bob', email: 'b@example.test' }
  appearance = 'light'
  await act(async () => window.dispatchEvent(new Event('focus')))
  await screen.findByText('Bob')
  await waitFor(() => expect(document.documentElement).not.toHaveClass('dark'))
  await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))
  await screen.findByRole('button', { name: 'Sign in' })
  expect(document.documentElement).not.toHaveClass('dark')
})

it('applies Forest dark as a dark palette and keeps standard Dark separate', async () => {
  let appearance = 'forest-dark'
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, init?: RequestInit) => {
      if (path === '/api/appearance' && init?.method === 'PUT') {
        appearance = JSON.parse(init.body as string).theme
        return { ok: true, status: 204 }
      }
      const body =
        path === '/auth/session'
          ? {
              configured: false,
              user: { id: 'alice', name: 'Alice', email: 'a@example.test' },
              csrf_token: 'csrf',
              appearance,
            }
          : path === '/api/settings'
            ? { allow_external_ai: false, vault_configured: false }
            : { items: [], next_cursor: null }
      return { ok: true, json: async () => body }
    }),
  )
  render(<App />)
  await screen.findByText('Alice')
  const root = document.documentElement
  await waitFor(() => expect(root).toHaveClass('dark', 'forest'))
  await userEvent.click(screen.getByRole('button', { name: 'Settings' }))
  expect(screen.getByLabelText('Color theme')).toHaveValue('forest-dark')
  await userEvent.selectOptions(screen.getByLabelText('Color theme'), 'dark')
  await userEvent.click(screen.getByRole('button', { name: 'Save appearance' }))
  await waitFor(() => expect(root).not.toHaveClass('forest'))
  expect(root).toHaveClass('dark')
  await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))
  await waitFor(() => expect(root).not.toHaveClass('dark'))
})
