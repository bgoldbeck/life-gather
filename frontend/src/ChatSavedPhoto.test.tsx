import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ChatPanel } from './ChatPanel'

vi.mock('./AssetProposalCard', () => ({
  AssetProposalCard: ({ id }: { id: string }) => (
    <section aria-label="Saved photo proposal">{id}</section>
  ),
}))
vi.mock('./ReceiptProposalCard', () => ({
  ReceiptProposalCard: ({ id }: { id: string }) => (
    <section aria-label="Saved photo receipt review">{id}</section>
  ),
}))

afterEach(() => vi.unstubAllGlobals())
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status })
const photo = {
  id: 'photo-private',
  filename: 'Synthetic nameplate.jpg',
  purpose: 'nameplate',
  updated_at: 100,
}
function harness({
  lose = false,
  pending = false,
  consent = true,
  usageFails = false,
  usage = 0,
  hasConnection = true,
  savedModel = 'synthetic-model',
  uploadResponse = undefined as Promise<Response> | undefined,
} = {}) {
  const writes: { path: string; body: Record<string, string> }[] = []
  const uploads: RequestInit[] = []
  let usageReads = 0
  const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
    if (path === '/api/settings') return json({ allow_external_ai: consent })
    if (path === '/api/credentials?limit=100')
      return json({
        items: hasConnection
          ? [
              {
                id: 'credential',
                kind: 'ai',
                provider: 'openai',
                label: 'Synthetic connection',
              },
            ]
          : [],
      })
    if (path === '/api/chat/preferences')
      return json({ credential_id: 'credential', model: savedModel })
    if (path === '/api/chat/usage')
      return json(
        { requests: usage },
        usageFails && ++usageReads > 1 ? 503 : 200,
      )
    if (path === '/api/chat/conversations' && init?.method !== 'POST')
      return json({
        items: [
          { id: 'current', title: 'Current conversation' },
          { id: 'other', title: 'Other conversation' },
        ],
        next_cursor: null,
      })
    if (path === '/api/chat/conversations' && init?.method === 'POST')
      return json({ id: 'new', title: 'New conversation' })
    if (path.startsWith('/api/photos?') && init?.method === 'POST') {
      uploads.push(init)
      if (uploadResponse) return uploadResponse
      return json(photo, 201)
    }
    if (path.startsWith('/api/photos?'))
      return json({ items: [photo], next_cursor: null })
    if (path.includes('/turns') && init?.method === 'POST') {
      const body = JSON.parse(String(init.body))
      writes.push({ path, body })
      if (lose && writes.length === 1)
        throw new Error('Synthetic lost response')
      if (pending && writes.length === 2)
        return json({
          id: 'turn',
          request_id: body.request_id,
          mode: body.mode,
          text: body.text,
          state: 'pending',
          result: {},
        })
      return json({
        id: 'turn',
        request_id: body.request_id,
        mode: body.mode,
        text: body.text,
        state: 'complete',
        result: {
          text: 'Unverified synthetic photo reading.',
          ...(body.mode === 'extract_photo_receipt'
            ? { receipt_proposal_id: 'receipt-proposal' }
            : { proposal_id: 'photo-proposal' }),
          sources: [{ id: 'source-photo', text: 'Synthetic transcription' }],
        },
      })
    }
    if (path.startsWith('/api/chat/sources/'))
      return json({
        id: 'source-photo',
        text: 'Synthetic transcription',
        next_offset: null,
      })
    if (path.includes('/turns')) return json({ items: [], next_cursor: null })
    throw new Error('Unexpected synthetic request: ' + path)
  })
  vi.stubGlobal('fetch', fetcher)
  return { writes, fetcher, uploads }
}
async function choosePhoto(mode = 'extract_photo') {
  const user = userEvent.setup()
  await user.selectOptions(await screen.findByLabelText('Action'), mode)
  await user.click(
    screen.getByRole('button', { name: 'Load saved Chat photos' }),
  )
  await user.click(
    await screen.findByRole('button', {
      name: 'Choose photo Synthetic nameplate.jpg',
    }),
  )
  return user
}

it('reads only an explicitly selected photo in the selected conversation and preserves a text draft', async () => {
  const { writes, fetcher } = harness()
  render(<ChatPanel csrfToken="csrf" />)
  const user = userEvent.setup()
  await user.click(
    await screen.findByRole('button', { name: 'Current conversation' }),
  )
  await user.type(
    screen.getByLabelText('Memory to save'),
    'Keep this unsent text draft.',
  )
  await user.selectOptions(screen.getByLabelText('Action'), 'extract_photo')
  expect(
    fetcher.mock.calls.some(([path]) => path.startsWith('/api/photos')),
  ).toBe(false)
  expect(
    screen.getByRole('button', { name: 'Read selected photo' }),
  ).toBeDisabled()
  await user.click(
    screen.getByRole('button', { name: 'Load saved Chat photos' }),
  )
  await user.click(
    await screen.findByRole('button', {
      name: 'Choose photo Synthetic nameplate.jpg',
    }),
  )
  expect(writes).toEqual([])
  await user.click(screen.getByRole('button', { name: 'Read selected photo' }))
  expect(
    await screen.findByRole('region', { name: 'Saved photo proposal' }),
  ).toHaveTextContent('photo-proposal')
  expect(writes).toHaveLength(1)
  expect(writes[0].path).toBe('/api/chat/conversations/current/turns')
  expect(writes[0].body).toMatchObject({
    mode: 'extract_photo',
    photo_id: photo.id,
    credential_id: 'credential',
    model: 'synthetic-model',
  })
  expect(writes[0].body).not.toHaveProperty('source_id')
  expect(JSON.stringify(writes[0].body)).not.toContain('Keep this unsent')
  await user.click(
    screen.getByRole('button', { name: 'Source 1: Synthetic transcription' }),
  )
  expect(
    await screen.findByRole('region', { name: 'Original evidence' }),
  ).toHaveTextContent('Synthetic transcription')
  await user.selectOptions(screen.getByLabelText('Action'), 'save')
  expect(screen.getByLabelText('Memory to save')).toHaveValue(
    'Keep this unsent text draft.',
  )
})

it('retains the exact photo request through lost response and pending retry', async () => {
  const { writes } = harness({ lose: true, pending: true })
  render(<ChatPanel csrfToken="csrf" />)
  const user = await choosePhoto()
  await user.click(screen.getByRole('button', { name: 'Read selected photo' }))
  await user.click(
    await screen.findByRole('button', { name: 'Retry same request' }),
  )
  expect(await screen.findByText(/still running/i)).toBeVisible()
  expect(screen.getByLabelText('Action')).toBeDisabled()
  expect(
    screen.getByRole('button', { name: 'Clear Chat photo' }),
  ).toBeDisabled()
  expect(screen.getByLabelText('AI connection')).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Retry same request' }))
  expect(
    await screen.findByRole('region', { name: 'Saved photo proposal' }),
  ).toBeVisible()
  expect(writes).toHaveLength(3)
  expect(writes[1]).toEqual(writes[0])
  expect(writes[2]).toEqual(writes[0])
})

it('does not send a selected photo without external AI consent', async () => {
  const { writes } = harness({ consent: false })
  render(<ChatPanel csrfToken="csrf" />)
  await choosePhoto()
  expect(
    screen.getByRole('button', { name: 'Read selected photo' }),
  ).toBeDisabled()
  expect(writes).toEqual([])
})

it.each(['connection', 'model', 'budget'])(
  'requires an available %s before reading a photo',
  async (gate) => {
    const { writes } = harness({
      hasConnection: gate !== 'connection',
      savedModel: gate === 'model' ? '' : 'synthetic-model',
      usage: gate === 'budget' ? 20 : 0,
    })
    render(<ChatPanel csrfToken="csrf" />)
    await choosePhoto()
    expect(
      screen.getByRole('button', { name: 'Read selected photo' }),
    ).toBeDisabled()
    expect(writes).toEqual([])
  },
)

it.each(['New conversation', 'Other conversation'])(
  'clears the photo choice on %s',
  async (destination) => {
    harness()
    render(<ChatPanel csrfToken="csrf" />)
    const user = await choosePhoto()
    expect(
      screen.getByRole('button', { name: 'Clear Chat photo' }),
    ).toBeEnabled()
    await user.click(screen.getByRole('button', { name: destination }))
    expect(
      screen.queryByRole('button', { name: 'Clear Chat photo' }),
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Read selected photo' }),
    ).toBeDisabled()
  },
)

it('does not call a saved reading uncertain when only daily usage refresh fails', async () => {
  const { writes } = harness({ usageFails: true })
  render(<ChatPanel csrfToken="csrf" />)
  const user = await choosePhoto()
  await user.click(screen.getByRole('button', { name: 'Read selected photo' }))
  expect(
    await screen.findByRole('region', { name: 'Saved photo proposal' }),
  ).toBeVisible()
  expect(
    await screen.findByText(
      /Request saved. Daily usage could not be refreshed/,
    ),
  ).toBeVisible()
  expect(screen.queryByText(/Connection lost/)).not.toBeInTheDocument()
  expect(
    screen.queryByRole('button', { name: 'Retry same request' }),
  ).not.toBeInTheDocument()
  expect(writes).toHaveLength(1)
})

it.each([
  [200, 'Other conversation'],
  [503, 'Other conversation'],
  [200, 'New conversation'],
  [503, 'New conversation'],
] as const)(
  'ignores old photo choices (%s) after %s',
  async (status, destination) => {
    const { fetcher } = harness()
    const regular = fetcher.getMockImplementation()!
    let release!: (response: Response) => void
    const late = new Promise<Response>((resolve) => {
      release = resolve
    })
    fetcher.mockImplementation(async (path, init) =>
      path.startsWith('/api/photos?') ? late : regular(path, init),
    )
    render(<ChatPanel csrfToken="csrf" />)
    const user = userEvent.setup()
    await user.selectOptions(
      await screen.findByLabelText('Action'),
      'extract_photo',
    )
    await user.click(
      screen.getByRole('button', { name: 'Load saved Chat photos' }),
    )
    await user.click(screen.getByRole('button', { name: destination }))
    await act(async () =>
      release(json({ items: [photo], next_cursor: null }, status)),
    )
    expect(
      screen.queryByRole('button', {
        name: 'Choose photo Synthetic nameplate.jpg',
      }),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  },
)

it('supports private photo paging and retrying failed metadata reads', async () => {
  const { fetcher, writes } = harness()
  const regular = fetcher.getMockImplementation()!
  let calls = 0
  fetcher.mockImplementation(async (path, init) => {
    if (!path.startsWith('/api/photos?')) return regular(path, init)
    calls++
    if (calls === 1) return json({}, 503)
    return json({
      items: [
        {
          ...photo,
          id: 'page-' + calls,
          filename: 'Synthetic ' + calls + '.jpg',
        },
      ],
      next_cursor: calls === 2 ? 'cursor' : null,
    })
  })
  render(<ChatPanel csrfToken="csrf" />)
  const user = userEvent.setup()
  await user.selectOptions(
    await screen.findByLabelText('Action'),
    'extract_photo',
  )
  await user.click(
    screen.getByRole('button', { name: 'Load saved Chat photos' }),
  )
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Unable to load saved photos',
  )
  await user.click(
    screen.getByRole('button', { name: 'Load saved Chat photos' }),
  )
  await user.click(
    await screen.findByRole('button', { name: 'More saved Chat photos' }),
  )
  expect(
    await screen.findByRole('button', { name: 'Choose photo Synthetic 3.jpg' }),
  ).toBeVisible()
  expect(
    screen.getByRole('button', { name: 'Choose photo Synthetic 2.jpg' }),
  ).toBeVisible()
  expect(
    fetcher.mock.calls.some(
      ([path]) => path === '/api/photos?limit=12&cursor=cursor',
    ),
  ).toBe(true)
  expect(writes).toEqual([])
})

it('uploads in the current Chat without reading automatically and preserves a text draft', async () => {
  const { writes, uploads, fetcher } = harness()
  render(<ChatPanel csrfToken="csrf" />)
  const user = userEvent.setup()
  await user.click(
    await screen.findByRole('button', { name: 'Current conversation' }),
  )
  await user.type(
    screen.getByLabelText('Memory to save'),
    'Keep this upload draft.',
  )
  await user.selectOptions(screen.getByLabelText('Action'), 'extract_photo')
  const original = new File(['synthetic image'], 'Synthetic nameplate.jpg', {
    type: 'image/jpeg',
  })
  await user.upload(screen.getByLabelText('Upload a photo in Chat'), original)
  expect(uploads).toHaveLength(0)
  await user.click(screen.getByRole('button', { name: 'Save photo privately' }))
  expect(
    await screen.findByText(
      /Photo saved privately. Uploading made no AI request/,
    ),
  ).toBeVisible()
  expect(uploads).toHaveLength(1)
  expect(uploads[0].body).toBe(original)
  expect(writes).toHaveLength(0)
  expect(
    fetcher.mock.calls.some(
      ([path, init]) =>
        path === '/api/chat/conversations' && init?.method === 'POST',
    ),
  ).toBe(false)
  expect(
    screen.getByRole('button', {
      name: 'Choose photo Synthetic nameplate.jpg',
    }),
  ).toHaveAttribute('aria-pressed', 'true')
  await user.selectOptions(screen.getByLabelText('Action'), 'save')
  expect(screen.getByLabelText('Memory to save')).toHaveValue(
    'Keep this upload draft.',
  )
  await user.selectOptions(screen.getByLabelText('Action'), 'extract_photo')
  await user.click(
    screen.getByRole('button', { name: 'Load saved Chat photos' }),
  )
  await user.click(
    await screen.findByRole('button', {
      name: 'Choose photo Synthetic nameplate.jpg',
    }),
  )
  await user.click(screen.getByRole('button', { name: 'Read selected photo' }))
  expect(
    await screen.findByRole('region', { name: 'Saved photo proposal' }),
  ).toBeVisible()
  expect(writes).toHaveLength(1)
  expect(writes[0].path).toBe('/api/chat/conversations/current/turns')
  expect(writes[0].body.photo_id).toBe(photo.id)
  expect(writes[0].body.text).not.toContain('upload draft')
})

it('can save a private Chat photo without external AI permission but cannot read it', async () => {
  const { uploads, writes } = harness({ consent: false, hasConnection: false })
  render(<ChatPanel csrfToken="csrf" />)
  const user = userEvent.setup()
  await screen.findByRole('button', { name: 'Current conversation' })
  await user.selectOptions(screen.getByLabelText('Action'), 'extract_photo')
  await user.upload(
    screen.getByLabelText('Upload a photo in Chat'),
    new File(['synthetic'], 'private.jpg', { type: 'image/jpeg' }),
  )
  await user.click(screen.getByRole('button', { name: 'Save photo privately' }))
  expect(
    await screen.findByText(
      /Photo saved privately. Uploading made no AI request/,
    ),
  ).toBeVisible()
  expect(uploads).toHaveLength(1)
  expect(writes).toHaveLength(0)
  expect(
    screen.getByRole('button', { name: 'Read selected photo' }),
  ).toBeDisabled()
})

it.each([201, 503])(
  'drops a late upload after New conversation and blocks reading an older selection while saving (%s)',
  async (status) => {
    let release!: (value: Response) => void
    const uploadResponse = new Promise<Response>((resolve) => {
      release = resolve
    })
    const { writes, uploads } = harness({ uploadResponse })
    render(<ChatPanel csrfToken="csrf" />)
    const user = await choosePhoto()
    expect(
      screen.getByRole('button', { name: 'Read selected photo' }),
    ).toBeEnabled()
    await user.upload(
      screen.getByLabelText('Upload a photo in Chat'),
      new File(['synthetic'], 'new.jpg', { type: 'image/jpeg' }),
    )
    await user.click(
      screen.getByRole('button', { name: 'Save photo privately' }),
    )
    expect(uploads).toHaveLength(1)
    expect(
      screen.getByRole('button', { name: 'Read selected photo' }),
    ).toBeDisabled()
    expect(
      screen.getByRole('button', { name: 'Load saved Chat photos' }),
    ).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'New conversation' }))
    await act(async () => release(json(photo, status)))
    expect(screen.queryByText(/Photo saved privately/)).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText(/Selected photo:/)).not.toBeInTheDocument()
    expect(writes).toHaveLength(0)
    expect(
      screen.getByRole('button', { name: 'Read selected photo' }),
    ).toBeDisabled()
  },
)

it('explicitly reviews a selected receipt photo in the current conversation while preserving text', async () => {
  const { writes } = harness()
  render(<ChatPanel csrfToken="csrf" />)
  const user = userEvent.setup()
  await user.click(
    await screen.findByRole('button', { name: 'Current conversation' }),
  )
  await user.type(
    screen.getByLabelText('Memory to save'),
    'Keep my receipt draft.',
  )
  await user.selectOptions(
    screen.getByLabelText('Action'),
    'extract_photo_receipt',
  )
  expect(
    screen.getByRole('button', { name: 'Review receipt photo' }),
  ).toBeDisabled()
  await user.click(
    screen.getByRole('button', { name: 'Load saved Chat photos' }),
  )
  await user.click(
    await screen.findByRole('button', {
      name: 'Choose photo Synthetic nameplate.jpg',
    }),
  )
  expect(writes).toHaveLength(0)
  await user.click(screen.getByRole('button', { name: 'Review receipt photo' }))
  expect(
    await screen.findByRole('region', { name: 'Saved photo receipt review' }),
  ).toBeVisible()
  expect(writes).toHaveLength(1)
  expect(writes[0].path).toBe('/api/chat/conversations/current/turns')
  expect(writes[0].body).toMatchObject({
    mode: 'extract_photo_receipt',
    photo_id: photo.id,
    text: 'Read receipt lines in this photo for human review.',
  })
  expect(writes[0].body.text).not.toContain('draft')
  expect(
    screen.queryByRole('region', { name: 'Saved photo proposal' }),
  ).not.toBeInTheDocument()
  await user.selectOptions(screen.getByLabelText('Action'), 'save')
  expect(screen.getByLabelText('Memory to save')).toHaveValue(
    'Keep my receipt draft.',
  )
})

it('preserves receipt photo mode, photo ID and exact arguments through lost and pending retries', async () => {
  const { writes } = harness({ lose: true, pending: true })
  render(<ChatPanel csrfToken="csrf" />)
  const user = await choosePhoto('extract_photo_receipt')
  await user.click(screen.getByRole('button', { name: 'Review receipt photo' }))
  await user.click(
    await screen.findByRole('button', { name: 'Retry same request' }),
  )
  expect(await screen.findByText(/still running/i)).toBeVisible()
  expect(screen.getByLabelText('Action')).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Retry same request' }))
  expect(
    await screen.findByRole('region', { name: 'Saved photo receipt review' }),
  ).toBeVisible()
  expect(writes).toHaveLength(3)
  expect(writes[1]).toEqual(writes[0])
  expect(writes[2]).toEqual(writes[0])
})

it.each([{ consent: false }, { usage: 20 }, { savedModel: '' }])(
  'keeps receipt photo reading behind configured AI gates: %j',
  async (settings) => {
    const { writes } = harness(settings)
    render(<ChatPanel csrfToken="csrf" />)
    await choosePhoto('extract_photo_receipt')
    expect(
      screen.getByRole('button', { name: 'Review receipt photo' }),
    ).toBeDisabled()
    expect(writes).toHaveLength(0)
  },
)

it('reuses a deliberately selected uploaded photo when changing from single-item to receipt mode', async () => {
  const { writes, uploads } = harness()
  render(<ChatPanel csrfToken="csrf" />)
  const user = userEvent.setup()
  await screen.findByRole('button', { name: 'Current conversation' })
  await user.selectOptions(screen.getByLabelText('Action'), 'extract_photo')
  await user.upload(
    screen.getByLabelText('Upload a photo in Chat'),
    new File(['synthetic'], 'receipt.jpg', { type: 'image/jpeg' }),
  )
  await user.click(screen.getByRole('button', { name: 'Save photo privately' }))
  await screen.findByText(/Photo saved privately/)
  await user.selectOptions(
    screen.getByLabelText('Action'),
    'extract_photo_receipt',
  )
  expect(
    screen.getByRole('button', { name: 'Review receipt photo' }),
  ).toBeEnabled()
  expect(uploads).toHaveLength(1)
  expect(writes).toHaveLength(0)
  await user.click(screen.getByRole('button', { name: 'Review receipt photo' }))
  expect(
    await screen.findByRole('region', { name: 'Saved photo receipt review' }),
  ).toBeVisible()
  expect(writes[0].body.photo_id).toBe(photo.id)
  await user.click(screen.getByRole('button', { name: 'New conversation' }))
  expect(
    screen.queryByRole('region', { name: 'Saved photo receipt review' }),
  ).not.toBeInTheDocument()
  expect(
    screen.getByRole('button', { name: 'Review receipt photo' }),
  ).toBeDisabled()
})
