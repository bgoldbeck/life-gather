import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => vi.unstubAllGlobals())

it.each([false, true])(
  'displays the running version with signed-in state %s',
  async (signedIn) => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          configured: false,
          user: signedIn
            ? { id: 'user', name: 'Tester', email: 'test@example.test' }
            : null,
          csrf_token: signedIn ? 'csrf' : null,
          build: {
            version: '0.3.0',
            revision: 'abcdef0123456789abcdef0123456789abcdef0123',
          },
        }),
      }),
    )
    render(<App />)
    expect(await screen.findByText('v0.3.0')).toBeVisible()
    expect(screen.getByText('abcdef0')).toHaveAttribute(
      'title',
      'Git revision abcdef0123456789abcdef0123456789abcdef0123',
    )
  },
)

it('does not invent a revision for an unlabelled source build', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        configured: false,
        user: null,
        csrf_token: null,
        build: { version: '0.3.0', revision: null },
      }),
    }),
  )
  render(<App />)
  expect(await screen.findByText('v0.3.0')).toBeVisible()
  expect(screen.getByText('Source build')).toBeVisible()
})
