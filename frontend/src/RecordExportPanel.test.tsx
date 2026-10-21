import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { RecordExportPanel } from './RecordExportPanel'
import { PrivateSettingsPanel } from './PrivateSettingsPanel'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})
function downloadHarness(
  response = Promise.resolve(
    new Response('{"format":"lifegather-records/1"}', {
      headers: { 'Content-Type': 'application/json' },
    }),
  ),
) {
  const fetcher = vi.fn(async () => response)
  vi.stubGlobal('fetch', fetcher)
  const create = vi.fn(() => 'blob:synthetic-export')
  const revoke = vi.fn()
  class ExportURL extends URL {
    static createObjectURL = create
    static revokeObjectURL = revoke
  }
  vi.stubGlobal('URL', ExportURL)
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, 'click')
    .mockImplementation(() => {})
  return { fetcher, create, revoke, click }
}

// Wire-envelope fixture only. Backend and browser tests inspect real ZIP entries.
function archiveEnvelope() {
  const bytes = new Uint8Array(64)
  bytes.set([80, 75, 3, 4])
  bytes.set([80, 75, 5, 6], bytes.length - 22)
  return bytes
}

it('downloads original evidence only after an explicit ZIP choice', async () => {
  const { fetcher, click, create, revoke } = downloadHarness(
    Promise.resolve(
      new Response(archiveEnvelope(), {
        headers: {
          'Content-Type': 'application/zip',
          'Content-Disposition':
            'attachment; filename="lifegather-archive-20261019T120000Z.zip"',
        },
      }),
    ),
  )
  const user = userEvent.setup()
  const view = render(<RecordExportPanel csrfToken="csrf-private" />)
  const choice = screen.getByLabelText(
    'Include original photos and documents (ZIP)',
  )
  expect(choice).not.toBeChecked()
  expect(fetcher).not.toHaveBeenCalled()
  await user.click(choice)
  expect(fetcher).not.toHaveBeenCalled()
  expect(screen.getByText(/ZIP includes records/)).toHaveTextContent(
    'not encrypted',
  )
  await user.click(
    screen.getByRole('button', { name: 'Download archive (ZIP)' }),
  )
  expect(await screen.findByRole('status')).toHaveTextContent(
    'records and originals download has started',
  )
  expect(fetcher).toHaveBeenCalledWith(
    '/api/export/archive',
    expect.objectContaining({
      method: 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      body: '{}',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'csrf-private',
      },
    }),
  )
  expect(create).toHaveBeenCalledOnce()
  expect(click).toHaveBeenCalledOnce()
  const anchor = click.mock.instances[0] as HTMLAnchorElement
  expect(anchor.download).toBe('lifegather-archive-20261019T120000Z.zip')
  expect(anchor.isConnected).toBe(false)
  view.unmount()
  expect(revoke).toHaveBeenCalledWith('blob:synthetic-export')
})

it('uses a safe ZIP filename when the server attachment name is unsafe', async () => {
  const { click } = downloadHarness(
    Promise.resolve(
      new Response(archiveEnvelope(), {
        headers: {
          'Content-Type': 'application/zip',
          'Content-Disposition': 'attachment; filename="../../escape.html"',
        },
      }),
    ),
  )
  const user = userEvent.setup()
  render(<RecordExportPanel csrfToken="csrf" />)
  await user.click(
    screen.getByLabelText('Include original photos and documents (ZIP)'),
  )
  await user.click(
    screen.getByRole('button', { name: 'Download archive (ZIP)' }),
  )
  await screen.findByRole('status')
  expect((click.mock.instances[0] as HTMLAnchorElement).download).toBe(
    'lifegather-archive.zip',
  )
})

it.each(['mime', 'header', 'footer', 'short'])(
  'refuses a malformed ZIP response without a download: %s',
  async (kind) => {
    let bytes = archiveEnvelope()
    if (kind === 'header') bytes[0] = 0
    if (kind === 'footer') bytes[bytes.length - 22] = 0
    if (kind === 'short') bytes = bytes.slice(0, 4)
    const { create, click } = downloadHarness(
      Promise.resolve(
        new Response(bytes, {
          headers: {
            'Content-Type':
              kind === 'mime' ? 'application/json' : 'application/zip',
          },
        }),
      ),
    )
    const user = userEvent.setup()
    render(<RecordExportPanel csrfToken="csrf" />)
    await user.click(
      screen.getByLabelText('Include original photos and documents (ZIP)'),
    )
    await user.click(
      screen.getByRole('button', { name: 'Download archive (ZIP)' }),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(/archive file/)
    expect(create).not.toHaveBeenCalled()
    expect(click).not.toHaveBeenCalled()
  },
)

it.each([413, 409])(
  'explains archive refusal %s and permits returning to JSON',
  async (status) => {
    const { create } = downloadHarness(
      Promise.resolve(new Response('{}', { status })),
    )
    const user = userEvent.setup()
    render(<RecordExportPanel csrfToken="csrf" />)
    await user.click(
      screen.getByLabelText('Include original photos and documents (ZIP)'),
    )
    await user.click(
      screen.getByRole('button', { name: 'Download archive (ZIP)' }),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(
      status === 413 ? 'exceeds the download limit' : 'could not be verified',
    )
    expect(create).not.toHaveBeenCalled()
    await user.click(
      screen.getByLabelText('Include original photos and documents (ZIP)'),
    )
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Download records (JSON)' }),
    ).toBeEnabled()
  },
)

it('locks archive choice while preparing and discards a late ZIP response after unmount', async () => {
  let finish!: (response: Response) => void
  const pending = new Promise<Response>((resolve) => {
    finish = resolve
  })
  const { fetcher, create } = downloadHarness(pending)
  const user = userEvent.setup()
  const view = render(<RecordExportPanel csrfToken="csrf" />)
  const choice = screen.getByLabelText(
    'Include original photos and documents (ZIP)',
  )
  await user.click(choice)
  const button = screen.getByRole('button', { name: 'Download archive (ZIP)' })
  fireEvent.click(button)
  fireEvent.click(button)
  expect(fetcher).toHaveBeenCalledOnce()
  expect(choice).toBeDisabled()
  expect(
    screen.getByRole('button', { name: 'Preparing archive…' }),
  ).toBeDisabled()
  view.unmount()
  await act(async () => {
    finish(
      new Response(archiveEnvelope(), {
        headers: { 'Content-Type': 'application/zip' },
      }),
    )
  })
  expect(create).not.toHaveBeenCalled()
})

it.each([
  'lifegather-records/1',
  'lifegather-records/2',
  'lifegather-records/3',
  'lifegather-records/4',
])(
  'downloads supported format %s only after an explicit private request',
  async (format) => {
    const { fetcher, create, click, revoke } = downloadHarness(
      Promise.resolve(
        new Response(JSON.stringify({ format }), {
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
    const user = userEvent.setup()
    const view = render(<RecordExportPanel csrfToken="csrf-private" />)
    expect(fetcher).not.toHaveBeenCalled()
    expect(
      screen.getByText(/Original images and document files/),
    ).toHaveTextContent('not a complete backup')
    expect(screen.getByText(/Up to 10,000 records/)).toHaveTextContent(
      'no partial file',
    )
    await user.click(
      screen.getByRole('button', { name: 'Download records (JSON)' }),
    )
    expect(await screen.findByRole('status')).toHaveTextContent(
      'download has started',
    )
    expect(fetcher).toHaveBeenCalledWith(
      '/api/export/records',
      expect.objectContaining({
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        body: '{}',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': 'csrf-private',
        },
      }),
    )
    expect(create).toHaveBeenCalledOnce()
    expect(click).toHaveBeenCalledOnce()
    const anchor = click.mock.instances[0] as HTMLAnchorElement
    expect(anchor.download).toBe('lifegather-records.json')
    expect(anchor.href).toBe('blob:synthetic-export')
    expect(anchor.isConnected).toBe(false)
    view.unmount()
    expect(revoke).toHaveBeenCalledWith('blob:synthetic-export')
  },
)

it('prevents duplicate clicks while preparing and ignores a response after unmount', async () => {
  let finish!: (response: Response) => void
  const response = new Promise<Response>((resolve) => {
    finish = resolve
  })
  const { fetcher, create, click } = downloadHarness(response)
  const view = render(<RecordExportPanel csrfToken="csrf" />)
  const button = screen.getByRole('button', { name: 'Download records (JSON)' })
  fireEvent.click(button)
  fireEvent.click(button)
  expect(fetcher).toHaveBeenCalledOnce()
  expect(
    screen.getByRole('button', { name: 'Preparing records…' }),
  ).toBeDisabled()
  const init = fetcher.mock.calls[0] as unknown as [string, RequestInit]
  view.unmount()
  expect(init[1].signal?.aborted).toBe(true)
  await act(async () =>
    finish(
      new Response('{}', { headers: { 'Content-Type': 'application/json' } }),
    ),
  )
  expect(create).not.toHaveBeenCalled()
  expect(click).not.toHaveBeenCalled()
})

it.each([
  [413, 'application/json', 'exceed the download limit'],
  [503, 'application/json', 'Unable to prepare'],
  [200, 'text/html', 'did not return a records file'],
])(
  'reports a %s response without downloading a misleading file',
  async (status, type, message) => {
    const { click } = downloadHarness(
      Promise.resolve(
        new Response('{}', { status, headers: { 'Content-Type': type } }),
      ),
    )
    render(<RecordExportPanel csrfToken="csrf" />)
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: 'Download records (JSON)' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(
      screen.getByRole('button', { name: 'Download records (JSON)' }),
    ).toBeEnabled()
    expect(click).not.toHaveBeenCalled()
  },
)

it('refreshes an expired session without starting a download', async () => {
  const { click } = downloadHarness(
    Promise.resolve(new Response('{}', { status: 401 })),
  )
  const refresh = vi.fn(async () => {})
  render(<RecordExportPanel csrfToken="csrf" refreshSession={refresh} />)
  await userEvent
    .setup()
    .click(screen.getByRole('button', { name: 'Download records (JSON)' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('session expired')
  expect(refresh).toHaveBeenCalledOnce()
  expect(click).not.toHaveBeenCalled()
})

it('recovers after a network failure without automatically retrying', async () => {
  const { fetcher, click } = downloadHarness()
  fetcher.mockRejectedValueOnce(new Error('Synthetic connection lost'))
  render(<RecordExportPanel csrfToken="csrf" />)
  const user = userEvent.setup()
  await user.click(
    screen.getByRole('button', { name: 'Download records (JSON)' }),
  )
  await screen.findByRole('alert')
  expect(fetcher).toHaveBeenCalledOnce()
  expect(click).not.toHaveBeenCalled()
  await user.click(
    screen.getByRole('button', { name: 'Download records (JSON)' }),
  )
  expect(await screen.findByRole('status')).toHaveTextContent(
    'download has started',
  )
  expect(fetcher).toHaveBeenCalledTimes(2)
})

it('releases a completed download URL after the browser has acquired it', async () => {
  const { revoke } = downloadHarness()
  vi.useFakeTimers()
  render(<RecordExportPanel csrfToken="csrf" />)
  await act(async () => {
    fireEvent.click(
      screen.getByRole('button', { name: 'Download records (JSON)' }),
    )
  })
  expect(revoke).not.toHaveBeenCalled()
  await act(async () => {
    vi.advanceTimersByTime(1000)
  })
  expect(revoke).toHaveBeenCalledWith('blob:synthetic-export')
})

it.each(['{"detail":"Unexpected response"}', '{invalid JSON'])(
  'rejects an invalid records document even with a successful JSON response',
  async (body) => {
    const { click } = downloadHarness(
      Promise.resolve(
        new Response(body, { headers: { 'Content-Type': 'application/json' } }),
      ),
    )
    render(<RecordExportPanel csrfToken="csrf" />)
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: 'Download records (JSON)' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'valid records file',
    )
    expect(click).not.toHaveBeenCalled()
  },
)

it.each([
  [
    'lifegather-records-20261019T000000Z.json',
    'lifegather-records-20261019T000000Z.json',
  ],
  ['../../unexpected.html', 'lifegather-records.json'],
])(
  'accepts a safe records filename and refuses %s path injection',
  async (filename, expected) => {
    const { click } = downloadHarness(
      Promise.resolve(
        new Response('{"format":"lifegather-records/1"}', {
          headers: {
            'Content-Type': 'application/json',
            'Content-Disposition': `attachment; filename="${filename}"`,
          },
        }),
      ),
    )
    render(<RecordExportPanel csrfToken="csrf" />)
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: 'Download records (JSON)' }))
    expect(await screen.findByRole('status')).toHaveTextContent(
      'download has started',
    )
    expect((click.mock.instances[0] as HTMLAnchorElement).download).toBe(
      expected,
    )
  },
)

it.each([0, 16 * 1024 * 1024 + 1])(
  'rejects an unexpected %i-byte file without downloading',
  async (size) => {
    const { click } = downloadHarness(
      Promise.resolve(
        new Response('x'.repeat(size), {
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
    render(<RecordExportPanel csrfToken="csrf" />)
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: 'Download records (JSON)' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'unexpected size',
    )
    expect(click).not.toHaveBeenCalled()
  },
)

it('ignores a body read that finishes after leaving Settings', async () => {
  let complete!: (value: Blob) => void
  const body = new Promise<Blob>((resolve) => {
    complete = resolve
  })
  const response = new Response('{}', {
    headers: { 'Content-Type': 'application/json' },
  })
  const read = vi.spyOn(response, 'blob').mockReturnValue(body)
  const { create } = downloadHarness(Promise.resolve(response))
  const view = render(<RecordExportPanel csrfToken="csrf" />)
  fireEvent.click(
    screen.getByRole('button', { name: 'Download records (JSON)' }),
  )
  await waitFor(() => expect(read).toHaveBeenCalledOnce())
  view.unmount()
  await act(async () =>
    complete(new Blob(['{"format":"lifegather-records/1"}'])),
  )
  expect(create).not.toHaveBeenCalled()
})

it('keeps record export available when credential settings fail to load', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response('{}', { status: 503 })),
  )
  render(<PrivateSettingsPanel csrfToken="csrf" />)
  await waitFor(() =>
    expect(screen.getByText('Settings unavailable.')).toBeVisible(),
  )
  expect(
    screen.getByRole('button', { name: 'Download records (JSON)' }),
  ).toBeEnabled()
})
