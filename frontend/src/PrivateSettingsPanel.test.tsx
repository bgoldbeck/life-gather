import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PrivateSettingsPanel } from './PrivateSettingsPanel'

const entry = {
  id: 'entry-1',
  kind: 'ai',
  provider: 'example',
  label: 'My provider',
}
const response = (body: unknown, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => body,
})
afterEach(() => vi.unstubAllGlobals())

describe('Private settings', () => {
  it('saves consent and credentials, replaces secrets, and removes entries', async () => {
    let items: unknown[] = []
    let consent = false
    const fetch = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === '/api/settings') {
        if (init?.method === 'PUT') {
          consent = JSON.parse(init.body as string).allow_external_ai
          return response(null, 204)
        }
        return response({ allow_external_ai: consent, vault_configured: true })
      }
      if (path === '/api/credentials' && !init?.method)
        return response({ items, next_cursor: null })
      if (init?.method === 'POST') {
        items = [entry]
        return response(entry, 201)
      }
      if (init?.method === 'PUT') return response(entry)
      if (init?.method === 'DELETE') {
        items = []
        return response(null, 204)
      }
      throw new Error('Unexpected request')
    })
    vi.stubGlobal('fetch', fetch)
    const user = userEvent.setup()
    render(<PrivateSettingsPanel csrfToken="fixture-csrf" />)
    await screen.findByText('No credentials saved.')
    expect(
      screen.getByRole('checkbox', { name: 'Allow external AI processing' }),
    ).not.toBeChecked()
    await user.click(
      screen.getByRole('checkbox', {
        name: 'Include original photos and PDFs (ZIP)',
      }),
    )
    expect(consent).toBe(false)
    expect(fetch).not.toHaveBeenCalledWith(
      '/api/settings',
      expect.objectContaining({ method: 'PUT' }),
    )
    await user.click(
      screen.getByRole('checkbox', { name: 'Allow external AI processing' }),
    )
    expect(await screen.findByText('Privacy preference saved.')).toBeVisible()
    expect(consent).toBe(true)
    await user.type(screen.getByLabelText('Provider'), 'example')
    await user.type(screen.getByLabelText('Label'), 'My provider')
    await user.type(
      screen.getByLabelText('API key or access token'),
      'synthetic-key',
    )
    await user.click(screen.getByRole('button', { name: 'Save credential' }))
    await screen.findByText('My provider')
    expect(screen.getByLabelText('API key or access token')).toHaveValue('')
    expect(screen.queryByText('synthetic-key')).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith(
      '/api/credentials',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'X-CSRF-Token': 'fixture-csrf' }),
      }),
    )
    await user.click(
      screen.getByRole('button', { name: 'Replace My provider' }),
    )
    await user.type(
      screen.getByLabelText('API key or access token'),
      'replacement-key',
    )
    await user.click(screen.getByRole('button', { name: 'Replace credential' }))
    await waitFor(() =>
      expect(
        screen.queryByText('Replace credential: My provider'),
      ).not.toBeInTheDocument(),
    )
    expect(fetch).toHaveBeenCalledWith(
      '/api/credentials/entry-1',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ secret: 'replacement-key' }),
      }),
    )
    await user.click(screen.getByRole('button', { name: 'Remove My provider' }))
    expect(await screen.findByText('No credentials saved.')).toBeVisible()
  })

  it('disables credential entry when the installation has no vault key', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (path: string) =>
        response(
          path === '/api/settings'
            ? { allow_external_ai: false, vault_configured: false }
            : { items: [], next_cursor: null },
        ),
      ),
    )
    render(<PrivateSettingsPanel csrfToken="fixture" />)
    await screen.findByText(/must configure a vault key/)
    expect(
      screen.getByRole('button', { name: 'Save credential' }),
    ).toBeDisabled()
    expect(
      screen.getByRole('checkbox', { name: 'Allow external AI processing' }),
    ).toBeEnabled()
  })

  it('clears a submitted secret even when saving fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (path: string, init?: RequestInit) => {
        if (init?.method) return response({}, 503)
        return response(
          path === '/api/settings'
            ? { allow_external_ai: false, vault_configured: true }
            : { items: [], next_cursor: null },
        )
      }),
    )
    render(<PrivateSettingsPanel csrfToken="fixture" />)
    await screen.findByText('No credentials saved.')
    await userEvent.type(screen.getByLabelText('Provider'), 'example')
    await userEvent.type(screen.getByLabelText('Label'), 'Example')
    await userEvent.type(
      screen.getByLabelText('API key or access token'),
      'secret-not-to-echo',
    )
    await userEvent.click(
      screen.getByRole('button', { name: 'Save credential' }),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Credential storage is unavailable',
    )
    expect(screen.getByLabelText('API key or access token')).toHaveValue('')
  })

  it('refreshes expired authentication and offers reload after failures', async () => {
    const refresh = vi.fn(async () => {})
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({}, 401)))
    render(
      <PrivateSettingsPanel csrfToken="fixture" refreshSession={refresh} />,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Your session expired',
    )
    expect(refresh).toHaveBeenCalled()
    expect(
      screen.getByRole('button', { name: 'Reload settings' }),
    ).toBeVisible()
  })
})
