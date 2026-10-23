import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AccountDeletion } from './AccountDeletion'

const reply = (body: unknown, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => body,
})
afterEach(() => vi.unstubAllGlobals())

describe('Account deletion', () => {
  it('needs the account email and acknowledgement, then signs out', async () => {
    const fetch = vi.fn(async () =>
      reply({ deleted: true, rows: 40, files: 2 }),
    )
    vi.stubGlobal('fetch', fetch)
    const refreshSession = vi.fn(async () => {})
    const user = userEvent.setup()
    render(
      <AccountDeletion
        email="sam@example.test"
        passwordEnabled={false}
        csrfToken="csrf"
        refreshSession={refreshSession}
      />,
    )
    const button = screen.getByRole('button', {
      name: 'Delete account permanently',
    })
    expect(button).toBeDisabled()
    await user.type(
      screen.getByLabelText(/Type your account email/),
      'other@example.test',
    )
    await user.click(screen.getByRole('checkbox'))
    expect(button).toBeDisabled()
    await user.clear(screen.getByLabelText(/Type your account email/))
    await user.type(
      screen.getByLabelText(/Type your account email/),
      'Sam@example.test',
    )
    expect(button).toBeEnabled()
    await user.click(button)
    await waitFor(() => expect(refreshSession).toHaveBeenCalled())
    expect(fetch).toHaveBeenCalledWith(
      '/api/account/delete',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf' }),
        body: JSON.stringify({ email: 'Sam@example.test' }),
      }),
    )
  })

  it('asks for the password and shows refusals', async () => {
    const fetch = vi.fn(async () =>
      reply(
        {
          detail:
            'Could not delete stored files; nothing else was deleted. Try again.',
        },
        503,
      ),
    )
    vi.stubGlobal('fetch', fetch)
    const refreshSession = vi.fn(async () => {})
    const user = userEvent.setup()
    render(
      <AccountDeletion
        email="sam@example.test"
        passwordEnabled
        csrfToken="csrf"
        refreshSession={refreshSession}
      />,
    )
    await user.type(
      screen.getByLabelText(/Type your account email/),
      'sam@example.test',
    )
    await user.click(screen.getByRole('checkbox'))
    const button = screen.getByRole('button', {
      name: 'Delete account permanently',
    })
    expect(button).toBeDisabled()
    await user.type(screen.getByLabelText('Current password'), 'secret')
    await user.click(button)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'nothing else was deleted',
    )
    expect(refreshSession).not.toHaveBeenCalled()
    expect(fetch).toHaveBeenCalledWith(
      '/api/account/delete',
      expect.objectContaining({
        body: JSON.stringify({ email: 'sam@example.test', password: 'secret' }),
      }),
    )
    // The password is cleared after a refusal.
    expect(screen.getByLabelText('Current password')).toHaveValue('')
  })
})
