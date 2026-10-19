import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ChatPanel } from './ChatPanel'

vi.mock('./AssetProposalCard', () => ({
  AssetProposalCard: ({ id }: { id: string }) => (
    <section aria-label="Saved photo proposal">{id}</section>
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
} = {}) {
  const writes: { path: string; body: Record<string, string> }[] = []
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
          mode: 'extract_photo',
          text: body.text,
          state: 'pending',
          result: {},
        })
      return json({
        id: 'turn',
        request_id: body.request_id,
        mode: 'extract_photo',
        text: body.text,
        state: 'complete',
        result: {
          text: 'Unverified synthetic photo reading.',
          proposal_id: 'photo-proposal',
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
  return { writes, fetcher }
}
async function choosePhoto() {
  const user = userEvent.setup()
  await user.selectOptions(
    await screen.findByLabelText('Action'),
    'extract_photo',
  )
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
      ([path]) => path === '/api/photos?limit=5&cursor=cursor',
    ),
  ).toBe(true)
  expect(writes).toEqual([])
})
