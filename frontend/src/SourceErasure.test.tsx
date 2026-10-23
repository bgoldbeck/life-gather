import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SourceErasure } from './SourceErasure'

const reply = (body: unknown, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => body,
})
const counts = {
  memories: 2,
  assets: 1,
  other_records: 0,
  facts: 3,
  purchases: 0,
  suggestions: 0,
  maintenance: 0,
  documents: 1,
  photos: 0,
  scans: 1,
  schedules: 0,
  connections: 1,
  kept_assets: 1,
  kept_records: 0,
}
afterEach(() => vi.unstubAllGlobals())

describe('Source erasure', () => {
  it('previews what goes, needs acknowledgement, then erases', async () => {
    const fetch = vi.fn(async (url: string) =>
      url.endsWith('/preview')
        ? reply({ counts, fingerprint: 'f'.repeat(64) })
        : reply({ erased: true, counts }),
    )
    vi.stubGlobal('fetch', fetch)
    const onErased = vi.fn()
    const user = userEvent.setup()
    render(
      <SourceErasure
        csrfToken="csrf"
        kind="mailbox"
        id="m1"
        name="owner@example.test"
        onErased={onErased}
      />,
    )
    await user.click(
      screen.getByRole('button', {
        name: 'Erase everything from this mailbox: owner@example.test',
      }),
    )
    expect(
      await screen.findByRole('heading', { name: 'Erase owner@example.test?' }),
    ).toBeInTheDocument()
    expect(screen.getByText('2 saved emails and memories')).toBeInTheDocument()
    expect(screen.getByText('1 asset')).toBeInTheDocument()
    expect(screen.getByText('1 document and its file')).toBeInTheDocument()
    expect(screen.queryByText(/purchase/)).not.toBeInTheDocument()
    expect(screen.getByText(/1 record stays because/)).toBeInTheDocument()
    const erase = screen.getByRole('button', { name: 'Erase permanently' })
    expect(erase).toBeDisabled()
    await user.click(screen.getByRole('checkbox'))
    await user.click(erase)
    await waitFor(() => expect(onErased).toHaveBeenCalled())
    expect(fetch).toHaveBeenLastCalledWith(
      '/api/erasure/erase',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf' }),
        body: JSON.stringify({
          kind: 'mailbox',
          id: 'm1',
          fingerprint: 'f'.repeat(64),
        }),
      }),
    )
  })

  it('shows the new list when the source changed since the preview', async () => {
    let previews = 0
    const fetch = vi.fn(async (url: string) => {
      if (url.endsWith('/preview')) {
        previews += 1
        return reply({
          counts: { ...counts, kept_assets: 0, assets: previews },
          fingerprint: String(previews).repeat(64),
        })
      }
      return reply(
        { detail: 'This source changed since the preview. Preview again.' },
        409,
      )
    })
    vi.stubGlobal('fetch', fetch)
    const onErased = vi.fn()
    const user = userEvent.setup()
    render(
      <SourceErasure
        csrfToken="csrf"
        kind="scan"
        id="r1"
        name="this scan"
        onErased={onErased}
      />,
    )
    await user.click(
      screen.getByRole('button', { name: 'Erase what this scan saved' }),
    )
    await user.click(await screen.findByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Erase permanently' }))
    expect(
      await screen.findByText(/changed since the preview/),
    ).toBeInTheDocument()
    expect(screen.getByText('2 assets')).toBeInTheDocument()
    // The acknowledgement must be given again for the new list.
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    expect(onErased).not.toHaveBeenCalled()
  })

  it('reports a refused preview, such as a running scan', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        reply({ detail: 'A scan of this source is still running.' }, 409),
      ),
    )
    const user = userEvent.setup()
    render(
      <SourceErasure csrfToken="csrf" kind="scan" id="r1" name="this scan" />,
    )
    await user.click(
      screen.getByRole('button', { name: 'Erase what this scan saved' }),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('still running')
  })
})
