import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ChatPanel } from './ChatPanel'

afterEach(() => vi.unstubAllGlobals())
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status })
const record = {
  page: 'Assets',
  entity_id: 'asset-1',
  version: 'a'.repeat(64),
  name: 'Synthetic dishwasher',
}

const saves: Record<string, unknown>[] = []
afterEach(() => {
  saves.length = 0
})

function harness() {
  const writes: Record<string, unknown>[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, init?: RequestInit) => {
      if (path === '/api/settings') return json({ allow_external_ai: true })
      if (path === '/api/credentials?limit=100')
        return json({
          items: [
            {
              id: 'credential',
              kind: 'ai',
              provider: 'anthropic',
              label: 'Synthetic connection',
            },
          ],
        })
      if (path === '/api/chat/preferences')
        return json({ credential_id: 'credential', model: 'synthetic-model' })
      if (path === '/api/chat/usage') return json({ requests: 0 })
      if (path === '/api/chat/conversations' && init?.method === 'POST')
        return json({ id: 'new', title: 'New conversation' })
      if (path === '/api/chat/conversations')
        return json({ items: [], next_cursor: null })
      if (path.includes('/turns') && init?.method === 'POST') {
        const body = JSON.parse(String(init.body))
        writes.push(body)
        return json({
          id: 'turn-' + writes.length,
          request_id: body.request_id,
          mode: body.mode,
          text: body.text,
          state: 'complete',
          result: {
            provider: 'anthropic',
            model: 'synthetic-model',
            text: 'Clean the filter monthly.',
            sources: [],
            research: {
              researched_at: '2026-10-22T08:30:15Z',
              queries: ['DW-100 manual'],
              searches: 1,
              shared_record: body.research.share_record
                ? { id: 'asset-1', name: 'Synthetic dishwasher' }
                : null,
              sources: [
                {
                  url: 'https://manuals.example.com/dw-100.pdf',
                  title: 'DW-100 Owner’s Manual',
                  published: 'March 3, 2024',
                  excerpt_kind: 'source',
                  excerpts: ['Clean the filter once a month.'],
                },
                {
                  url: 'https://www.example.com/specs',
                  title: 'DW-100 specifications',
                  published: null,
                  excerpt_kind: 'source',
                  excerpts: [],
                },
              ],
              identity_note:
                'Web results describe a product model, not your own item.',
            },
          },
        })
      }
      if (path === '/api/research-findings' && init?.method === 'POST') {
        const body = JSON.parse(String(init.body))
        saves.push({
          ...body,
          csrf: new Headers(init.headers).get('X-CSRF-Token'),
        })
        return json({ id: 'finding', already_saved: saves.length > 1 }, 201)
      }
      if (path.includes('/turns')) return json({ items: [], next_cursor: null })
      throw new Error('Unexpected synthetic request: ' + path)
    }),
  )
  return writes
}

it('sends only typed text unless the record is shared and shows dated citations', async () => {
  const writes = harness()
  render(<ChatPanel csrfToken="csrf" context={record} />)
  const user = userEvent.setup()
  await user.selectOptions(await screen.findByLabelText('Action'), 'research')
  expect(
    screen.getByText(/receive only the text you type\. No other memories/),
  ).toBeInTheDocument()
  const share = screen.getByRole('checkbox', {
    name: /Share the saved name and details of Synthetic dishwasher/,
  })
  expect(share).not.toBeChecked()
  await user.type(screen.getByLabelText('What to look up'), 'DW-100 manual')
  await user.click(screen.getByRole('button', { name: 'Research on the web' }))
  expect(await screen.findByText('Clean the filter monthly.')).toBeVisible()
  expect(writes[0]).toMatchObject({
    mode: 'research',
    text: 'DW-100 manual',
    credential_id: 'credential',
    research: { share_record: false },
  })
  const sources = screen.getByRole('region', { name: 'Web research sources' })
  expect(
    within(sources).getByText(/No saved record details shared/),
  ).toBeVisible()
  const link = within(sources).getByRole('link', {
    name: 'DW-100 Owner’s Manual',
  })
  expect(link).toHaveAttribute('href', 'https://manuals.example.com/dw-100.pdf')
  expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  expect(within(sources).getByText('Page dated March 3, 2024')).toBeVisible()
  expect(within(sources).getByText('Page date not reported')).toBeVisible()
  expect(within(sources).getByText('Searches run: DW-100 manual')).toBeVisible()
  expect(within(sources).getByRole('note')).toHaveTextContent(
    'not your own item',
  )

  await user.click(share)
  expect(
    screen.getByText(/plus the saved name and details of Synthetic dishwasher/),
  ).toBeInTheDocument()
  await user.type(screen.getByLabelText('What to look up'), 'filter part')
  await user.click(screen.getByRole('button', { name: 'Research on the web' }))
  expect(
    await screen.findByText(/Shared saved details of Synthetic dishwasher/),
  ).toBeVisible()
  expect(writes[1]).toMatchObject({ research: { share_record: true } })
  // Sharing is per request.
  expect(share).not.toBeChecked()
})

it('cannot share record details without a selected record', async () => {
  harness()
  render(
    <ChatPanel
      csrfToken="csrf"
      context={{ page: 'Settings', entity_id: null, version: '' }}
    />,
  )
  const user = userEvent.setup()
  await user.selectOptions(await screen.findByLabelText('Action'), 'research')
  expect(
    screen.getByRole('checkbox', {
      name: 'Open a record to optionally share its saved details',
    }),
  ).toBeDisabled()
})

it('saves a cited source to the open asset only when asked', async () => {
  const writes = harness()
  const announced = vi.fn()
  window.addEventListener('lifegather:research-finding-saved', announced)
  render(<ChatPanel csrfToken="csrf" context={record} />)
  const user = userEvent.setup()
  await user.selectOptions(await screen.findByLabelText('Action'), 'research')
  await user.type(screen.getByLabelText('What to look up'), 'DW-100 manual')
  await user.click(screen.getByRole('button', { name: 'Research on the web' }))
  const sources = await screen.findByRole('region', {
    name: 'Web research sources',
  })
  const buttons = within(sources).getAllByRole('button', {
    name: 'Save to Synthetic dishwasher',
  })
  expect(buttons).toHaveLength(2)
  // Nothing is saved until a source's button is pressed.
  expect(saves).toEqual([])
  await user.click(buttons[0])
  expect(
    await within(sources).findByText('Saved to Synthetic dishwasher'),
  ).toBeVisible()
  expect(saves).toHaveLength(1)
  expect(saves[0]).toMatchObject({
    turn_id: 'turn-1',
    url: 'https://manuals.example.com/dw-100.pdf',
    asset_id: 'asset-1',
    csrf: 'csrf',
  })
  expect(Object.keys(saves[0]).sort()).toEqual(
    ['asset_id', 'csrf', 'request_id', 'turn_id', 'url'].sort(),
  )
  expect(writes).toHaveLength(1)
  expect(announced).toHaveBeenCalledTimes(1)
  window.removeEventListener('lifegather:research-finding-saved', announced)
})

it('asks to open an asset before saving a source', async () => {
  harness()
  render(
    <ChatPanel
      csrfToken="csrf"
      context={{ page: 'Profiles', entity_id: 'person-1', version: 'b' }}
    />,
  )
  const user = userEvent.setup()
  await user.selectOptions(await screen.findByLabelText('Action'), 'research')
  await user.type(screen.getByLabelText('What to look up'), 'DW-100 manual')
  await user.click(screen.getByRole('button', { name: 'Research on the web' }))
  const sources = await screen.findByRole('region', {
    name: 'Web research sources',
  })
  expect(within(sources).queryByRole('button', { name: /^Save to/ })).toBeNull()
  expect(
    within(sources).getByText(/Open an asset to save a source/),
  ).toBeVisible()
})
