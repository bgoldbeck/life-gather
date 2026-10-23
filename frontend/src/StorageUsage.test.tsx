import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { formatBytes } from './formatBytes'
import { StorageUsage } from './StorageUsage'

const reply = (body: unknown, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => body,
})
afterEach(() => vi.unstubAllGlobals())

const usage = {
  used_bytes: 3 * 1024 * 1024,
  photos: 2,
  photo_bytes: 2 * 1024 * 1024,
  documents: 1,
  document_bytes: 1024 * 1024,
}

describe('Storage usage', () => {
  it('shows usage with no limit by default', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        reply({ ...usage, limit_bytes: null, available_bytes: null }),
      ),
    )
    render(<StorageUsage />)
    expect(await screen.findByText('3.0 MB used · No limit')).toBeVisible()
    expect(screen.getByText('Photos: 2 (2.0 MB)')).toBeVisible()
    expect(screen.getByText('Documents: 1 (1.0 MB)')).toBeVisible()
    expect(screen.queryByRole('progressbar')).toBeNull()
  })

  it('shows the limit and warns when full', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        reply({ ...usage, limit_bytes: 3 * 1024 * 1024, available_bytes: 0 }),
      ),
    )
    render(<StorageUsage />)
    expect(await screen.findByText('3.0 MB of 3.0 MB used')).toBeVisible()
    expect(
      screen.getByRole('progressbar', { name: 'Storage used' }),
    ).toHaveAttribute('value', String(3 * 1024 * 1024))
    expect(screen.getByRole('alert')).toHaveTextContent('Your storage is full')
  })

  it('reports a failed load and refreshes an expired session', async () => {
    const refreshSession = vi.fn(async () => {})
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => reply({}, 401)),
    )
    render(<StorageUsage refreshSession={refreshSession} />)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Unable to load storage usage.',
    )
    expect(refreshSession).toHaveBeenCalled()
  })

  it('formats sizes', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(256 * 1024 * 1024)).toBe('256 MB')
  })
})
