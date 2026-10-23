import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { RecordRestorePanel } from './RecordRestorePanel'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

function archive() {
  return new File([new Uint8Array([80, 75, 3, 4])], 'lifegather-archive.zip', {
    type: 'application/zip',
  })
}

it('restores a chosen archive only after confirmation and shows counts', async () => {
  const fetcher = vi.fn(
    async (_url: string, _init?: RequestInit) =>
      new Response(
        JSON.stringify({
          snapshot_at: '2026-10-22T08:00:00+00:00',
          counts: {},
          total_records: 1234,
          originals: 3,
        }),
        { headers: { 'Content-Type': 'application/json' } },
      ),
  )
  vi.stubGlobal('fetch', fetcher)
  const user = userEvent.setup()
  render(<RecordRestorePanel csrfToken="csrf-private" />)
  const button = screen.getByRole('button', { name: 'Restore archive' })
  expect(button).toBeDisabled()
  const file = archive()
  await user.upload(screen.getByLabelText('Personal archive (ZIP)'), file)
  expect(button).toBeDisabled()
  await user.click(
    screen.getByLabelText("Add this archive's records to my account"),
  )
  await user.click(button)
  await screen.findByText(/Restored 1,234 records and 3 original files/)
  expect(fetcher).toHaveBeenCalledTimes(1)
  const [url, init] = fetcher.mock.calls[0]
  expect(url).toBe('/api/import/archive')
  expect(init?.method).toBe('POST')
  expect(init?.body).toBe(file)
  expect(init?.headers).toMatchObject({
    'Content-Type': 'application/zip',
    'X-CSRF-Token': 'csrf-private',
  })
  expect(button).toBeDisabled()
})

it('reports records already in the account and an archive with nothing new', async () => {
  const reply = (total: number, present: number, originals: number) =>
    new Response(
      JSON.stringify({
        snapshot_at: '2026-10-22T08:00:00+00:00',
        counts: {},
        total_records: total,
        already_present: present,
        originals,
      }),
      { headers: { 'Content-Type': 'application/json' } },
    )
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(reply(12, 300, 1))
    .mockResolvedValueOnce(reply(0, 312, 0))
  vi.stubGlobal('fetch', fetcher)
  const user = userEvent.setup()
  render(<RecordRestorePanel csrfToken="csrf-private" />)
  for (const expected of [
    /Restored 12 records and 1 original files.*300 records were already in your account and were left unchanged/,
    /Nothing new to restore.*312 records were already in your account/,
  ]) {
    await user.upload(
      screen.getByLabelText('Personal archive (ZIP)'),
      archive(),
    )
    await user.click(
      screen.getByLabelText("Add this archive's records to my account"),
    )
    await user.click(screen.getByRole('button', { name: 'Restore archive' }))
    expect(await screen.findByRole('status')).toHaveTextContent(expected)
  }
})

it('explains a refused restore and keeps the chosen file', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            detail:
              'Records in this archive belong to another account in this installation.',
          }),
          { status: 409, headers: { 'Content-Type': 'application/json' } },
        ),
    ),
  )
  const user = userEvent.setup()
  render(<RecordRestorePanel csrfToken="csrf-private" />)
  await user.upload(screen.getByLabelText('Personal archive (ZIP)'), archive())
  await user.click(
    screen.getByLabelText("Add this archive's records to my account"),
  )
  await user.click(screen.getByRole('button', { name: 'Restore archive' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Records in this archive belong to another account',
  )
  await waitFor(() =>
    expect(
      screen.getByRole('button', { name: 'Restore archive' }),
    ).toBeEnabled(),
  )
})

it('reports invalid archives without claiming anything was saved', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            detail: 'Archive original does not match its hash',
          }),
          { status: 422, headers: { 'Content-Type': 'application/json' } },
        ),
    ),
  )
  const user = userEvent.setup()
  render(<RecordRestorePanel csrfToken="csrf-private" />)
  await user.upload(screen.getByLabelText('Personal archive (ZIP)'), archive())
  await user.click(
    screen.getByLabelText("Add this archive's records to my account"),
  )
  await user.click(screen.getByRole('button', { name: 'Restore archive' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Archive original does not match its hash. Nothing was restored.',
  )
})
