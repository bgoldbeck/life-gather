import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { PhotosPanel } from './PhotosPanel'

afterEach(() => vi.unstubAllGlobals())
const photo = {
  id: 'photo',
  filename: 'plate.jpg',
  purpose: 'nameplate',
  size: 1000,
  width: 200,
  height: 100,
  updated_at: 5,
  source_id: null,
  deleted_at: null,
}

it('uploads privately into an existing gallery without automatically using AI', async () => {
  const user = userEvent.setup()
  const calls: { url: string; init?: RequestInit }[] = []
  let saved = false
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      let result: unknown = { items: [], next_cursor: null }
      if (url.startsWith('/api/photos?') && init?.method === 'POST') {
        saved = true
        result = photo
      } else if (url.startsWith('/api/photos?'))
        result = { items: saved ? [photo] : [], next_cursor: null }
      else if (url === '/api/settings') result = { allow_external_ai: false }
      return new Response(JSON.stringify(result))
    }),
  )
  render(<PhotosPanel csrfToken="csrf" assetId="asset" />)
  await screen.findByText('No photos saved here yet.')
  await user.upload(
    screen.getByLabelText('Photo file'),
    new File(['synthetic'], 'plate.jpg', { type: 'image/jpeg' }),
  )
  await user.selectOptions(screen.getByLabelText('Photo purpose'), 'nameplate')
  await user.click(
    screen.getByRole('button', { name: 'Upload privately to this item' }),
  )
  await screen.findByText('Photo saved privately. No AI request was made.')
  const upload = calls.find((call) => call.init?.method === 'POST')!
  expect(upload.url).toBe('/api/photos?purpose=nameplate&asset_id=asset')
  expect(upload.init?.headers).toMatchObject({
    'X-CSRF-Token': 'csrf',
    'X-File-Name': 'plate.jpg',
    'Content-Type': 'application/octet-stream',
  })
  expect(calls.some((call) => call.url.includes('/turns'))).toBe(false)
  expect(
    screen.getByRole('link', { name: 'Download original' }),
  ).toHaveAttribute('href', '/api/photos/photo/original')
  await user.click(screen.getByText('Read photo with AI'))
  expect(screen.getByRole('button', { name: 'Read this photo' })).toBeDisabled()
  await user.click(screen.getByText('Delete this photo'))
  expect(
    screen.getByRole('button', { name: 'Delete original and preview' }),
  ).toBeDisabled()
})

it('requires a deliberate selected connection and preserves the same AI request after connection loss', async () => {
  const user = userEvent.setup()
  const turnBodies: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      let result: unknown = { items: [photo], next_cursor: null }
      if (url === '/api/credentials?limit=100')
        result = {
          items: [
            {
              id: 'credential',
              provider: 'openai',
              kind: 'ai',
              label: 'Synthetic OpenAI',
            },
          ],
        }
      else if (url === '/api/settings') result = { allow_external_ai: true }
      else if (url === '/api/chat/conversations')
        result = { id: 'conversation' }
      else if (url.includes('/turns')) {
        turnBodies.push(String(init?.body))
        if (turnBodies.length === 1) throw new TypeError('Disconnected')
        result = {
          state: 'failed',
          result: { text: 'Synthetic failed request. No retry.' },
        }
      } else if (url === '/api/photos/photo') result = photo
      return new Response(JSON.stringify(result))
    }),
  )
  render(<PhotosPanel csrfToken="csrf" />)
  await user.click(await screen.findByRole('button', { name: /plate.jpg/ }))
  await user.click(screen.getByText('Read photo with AI'))
  await user.selectOptions(screen.getByLabelText('AI connection'), 'credential')
  await user.type(
    screen.getByLabelText('Vision-capable model'),
    'synthetic-vision',
  )
  await user.click(screen.getByRole('button', { name: 'Read this photo' }))
  await user.click(
    await screen.findByRole('button', { name: 'Check same photo request' }),
  )
  await screen.findByText('Synthetic failed request. No retry.')
  expect(turnBodies).toHaveLength(2)
  expect(turnBodies[0]).toBe(turnBodies[1])
  expect(JSON.parse(turnBodies[0])).toMatchObject({
    mode: 'extract_photo',
    photo_id: 'photo',
    credential_id: 'credential',
    model: 'synthetic-vision',
  })
  await waitFor(() =>
    expect(screen.getByLabelText('AI connection')).toBeEnabled(),
  )
})
