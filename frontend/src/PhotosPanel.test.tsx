import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { PhotosPanel } from './PhotosPanel'

vi.mock('./ReceiptProposalCard', () => ({
  ReceiptProposalCard: ({ id }: { id: string }) => (
    <section aria-label="Existing photo receipt">{id}</section>
  ),
}))

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

it('removes only a gallery link and keeps the original photo private', async () => {
  const user = userEvent.setup()
  const calls: { url: string; init?: RequestInit }[] = []
  let detached = false
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      if (url === '/api/photos/detach') {
        detached = true
        return new Response(JSON.stringify({ ...photo, updated_at: 6 }))
      }
      if (url === '/api/photos/attach') {
        detached = false
        return new Response(JSON.stringify({ ...photo, updated_at: 7 }))
      }
      if (url === '/api/settings')
        return new Response(JSON.stringify({ allow_external_ai: false }))
      return new Response(
        JSON.stringify({ items: detached ? [] : [photo], next_cursor: null }),
      )
    }),
  )
  render(<PhotosPanel csrfToken="csrf" assetId="asset" />)
  await user.click(await screen.findByRole('button', { name: /plate.jpg/ }))
  await user.click(
    screen.getByRole('button', { name: 'Remove photo from this item' }),
  )
  await screen.findByText(/Photo removed from this item. The original/)
  const detach = calls.find((c) => c.url === '/api/photos/detach')!
  expect(JSON.parse(String(detach.init?.body))).toEqual({
    photo_id: 'photo',
    asset_id: 'asset',
    expected_updated_at: 5,
  })
  expect(detach.init?.headers).toMatchObject({ 'X-CSRF-Token': 'csrf' })
  expect(calls.some((c) => c.url.includes('/delete'))).toBe(false)
  expect(
    screen.queryByRole('button', { name: /plate.jpg/ }),
  ).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Undo photo removal' }))
  await screen.findByText('Photo attached to this item again.')
  const attach = calls.find((c) => c.url === '/api/photos/attach')!
  expect(JSON.parse(String(attach.init?.body))).toEqual({
    photo_id: 'photo',
    asset_id: 'asset',
    expected_updated_at: 6,
  })
  expect(attach.init?.headers).toMatchObject({ 'X-CSRF-Token': 'csrf' })
  expect(
    await screen.findByRole('button', { name: /plate.jpg/ }),
  ).toBeInTheDocument()
  expect(
    screen.queryByRole('button', { name: 'Undo photo removal' }),
  ).not.toBeInTheDocument()
})

it('displays an existing multi-item photo receipt returned by photo reading and clears it on selection change', async () => {
  const user = userEvent.setup()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      let result: unknown = { items: [], next_cursor: null }
      if (url.startsWith('/api/photos?'))
        result = {
          items: [photo, { ...photo, id: 'other', filename: 'other.jpg' }],
          next_cursor: null,
        }
      else if (url === '/api/settings') result = { allow_external_ai: true }
      else if (url === '/api/credentials?limit=100')
        result = {
          items: [
            {
              id: 'credential',
              kind: 'ai',
              provider: 'openai',
              label: 'Synthetic',
            },
          ],
        }
      else if (url === '/api/chat/conversations' && init?.method === 'POST')
        result = { id: 'conversation' }
      else if (url.includes('/turns'))
        result = {
          state: 'complete',
          result: {
            text: 'Existing receipt review.',
            receipt_proposal_id: 'receipt',
          },
        }
      else if (url === '/api/photos/photo') result = photo
      return new Response(JSON.stringify(result))
    }),
  )
  render(<PhotosPanel csrfToken="csrf" />)
  await user.click(await screen.findByRole('button', { name: /plate.jpg/ }))
  await user.click(screen.getByText('Read photo with AI'))
  await user.selectOptions(screen.getByLabelText('AI connection'), 'credential')
  await user.type(screen.getByLabelText('Vision-capable model'), 'synthetic')
  await user.click(screen.getByRole('button', { name: 'Read this photo' }))
  expect(
    await screen.findByRole('region', { name: 'Existing photo receipt' }),
  ).toHaveTextContent('receipt')
  await user.click(screen.getByRole('button', { name: /other.jpg/ }))
  expect(
    screen.queryByRole('region', { name: 'Existing photo receipt' }),
  ).not.toBeInTheDocument()
})

it('opens the saved email a photo attachment came from', async () => {
  const user = userEvent.setup()
  const urls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      urls.push(url)
      let result: unknown = { items: [photo], next_cursor: null }
      if (url === '/api/photos/photo/email-sources')
        result = {
          items: [{ source_id: 'email-source', filename: 'plate.jpg' }],
        }
      else if (url === '/api/chat/sources/email-source')
        result = {
          id: 'email-source',
          text: 'Subject: Synthetic order\n\nAttachment: plate.jpg',
        }
      else if (url === '/api/settings') result = { allow_external_ai: false }
      else if (url.startsWith('/api/credentials')) result = { items: [] }
      return new Response(JSON.stringify(result))
    }),
  )
  render(<PhotosPanel csrfToken="csrf" />)
  await user.click(await screen.findByRole('button', { name: /plate\.jpg/ }))
  await user.click(
    await screen.findByRole('button', {
      name: 'Open the email this photo came from',
    }),
  )
  expect(await screen.findByText(/Attachment: plate\.jpg/)).toBeVisible()
  expect(urls).toContain('/api/chat/sources/email-source')
})
