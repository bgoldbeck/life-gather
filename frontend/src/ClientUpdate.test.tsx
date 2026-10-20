import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'
import { ClientUpdateNotice } from './ClientUpdate'
import { buildChanged } from './clientBuild'

afterEach(() => vi.unstubAllGlobals())

it('detects version, rollback and same-version revision changes without guessing missing revisions', () => {
  const build = { version: '0.58.0', revision: 'a'.repeat(40) }
  expect(buildChanged(build, build)).toBe(false)
  expect(buildChanged(build, { ...build, revision: 'b'.repeat(40) })).toBe(true)
  expect(buildChanged(build, { version: '0.57.0', revision: null })).toBe(true)
  expect(buildChanged(build, { ...build, revision: null })).toBe(false)
  expect(buildChanged(build, undefined)).toBe(false)
})

it('reloads only on an explicit button click and explains draft loss', async () => {
  const reload = vi.fn()
  render(
    <ClientUpdateNotice
      loaded={{ version: '0.58.0', revision: null }}
      current={{ version: '0.58.1', revision: null }}
      onReload={reload}
    />,
  )
  expect(screen.getByRole('status')).toHaveTextContent(
    'Unsaved drafts will be lost',
  )
  expect(reload).not.toHaveBeenCalled()
  await userEvent.click(
    screen.getByRole('button', { name: 'Reload LifeGather' }),
  )
  expect(reload).toHaveBeenCalledOnce()
})

it('keeps the executing UI version and unsent draft when a focus check discovers deployment', async () => {
  let build = { version: '0.58.0', revision: 'a'.repeat(40) }
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string) =>
      Response.json(
        path === '/auth/session'
          ? {
              configured: true,
              user: { id: 'alice', name: 'Alice', email: 'alice@example.test' },
              csrf_token: 'csrf',
              build,
            }
          : path === '/api/chat/context'
            ? { page: 'Overview', entity_id: null, version: '' }
            : { items: [], next_cursor: null },
      ),
    ),
  )
  render(<App />)
  await screen.findByText('Alice')
  await userEvent.type(
    screen.getByLabelText('Message your assistant'),
    'Keep this unsent draft',
  )
  build = { version: '0.58.1', revision: 'b'.repeat(40) }
  await act(async () => window.dispatchEvent(new Event('focus')))
  await screen.findByRole('button', { name: 'Reload LifeGather' })
  expect(screen.getByLabelText('Message your assistant')).toHaveValue(
    'Keep this unsent draft',
  )
  expect(
    within(screen.getByLabelText('Application version')).getByText('v0.58.0'),
  ).toBeVisible()
  expect(
    screen.getByRole('navigation', { name: 'Main navigation' }),
  ).toBeVisible()
})
