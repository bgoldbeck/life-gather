import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ChatPanel } from './ChatPanel'
import { ChatEmailScan } from './ChatEmailScan'

afterEach(() => vi.unstubAllGlobals())
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status })
const mailboxes = {
  items: [
    { id: 'mailbox', address: 'synthetic@example.test', connected: true },
    { id: 'removed', address: 'removed@example.test', connected: false },
  ],
}
function harness(lose = false) {
  const writes: { path: string; body: Record<string, unknown> }[] = []
  const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
    if (path === '/api/settings') return json({ allow_external_ai: false })
    if (path === '/api/credentials?limit=100') return json({ items: [] })
    if (path === '/api/chat/preferences') return json({})
    if (path === '/api/chat/usage') return json({ requests: 20 })
    if (path === '/api/mailboxes') return json(mailboxes)
    if (path === '/api/chat/conversations' && init?.method !== 'POST')
      return json({ items: [{ id: 'current', title: 'Current conversation' }] })
    if (path === '/api/chat/conversations' && init?.method === 'POST')
      return json({ id: 'new', title: 'New conversation' })
    if (path.includes('/turns') && init?.method === 'POST') {
      const body = JSON.parse(String(init.body))
      writes.push({ path, body })
      if (lose && writes.length === 1)
        throw new Error('Synthetic lost response')
      return json({
        id: 'turn',
        request_id: body.request_id,
        mode: body.mode,
        text: body.text,
        state: 'complete',
        result: { text: 'Email scan queued.', scan_run_id: 'run-private' },
      })
    }
    if (path.endsWith('/turns')) return json({ items: [], next_cursor: null })
    throw new Error('Unexpected synthetic URL: ' + path)
  })
  vi.stubGlobal('fetch', fetcher)
  return { writes, fetcher }
}

async function chooseScan() {
  const user = userEvent.setup()
  await user.click(
    await screen.findByRole('button', { name: 'Current conversation' }),
  )
  await user.selectOptions(screen.getByLabelText('Action'), 'scan_email')
  await screen.findByRole('option', { name: 'synthetic@example.test' })
  await user.selectOptions(
    screen.getByLabelText('Email scan mailbox'),
    'mailbox',
  )
  return user
}

it('queues only an explicit scope without AI permission and opens the saved job', async () => {
  const { writes } = harness()
  const open = vi.fn()
  render(<ChatPanel csrfToken="csrf" onOpenScan={open} />)
  const user = await chooseScan()
  expect(writes).toEqual([])
  expect(
    screen.queryByRole('option', { name: 'removed@example.test' }),
  ).toBeNull()
  expect(screen.queryByLabelText('AI connection')).toBeNull()
  await user.type(screen.getByLabelText('Email filter (optional)'), 'receipt')
  fireEvent.change(screen.getByLabelText('Maximum messages'), {
    target: { value: '5' },
  })
  const before = Math.floor(Date.now() / 1000)
  await user.click(screen.getByRole('button', { name: 'Start email scan' }))
  await user.click(
    await screen.findByRole('button', { name: 'View email scan' }),
  )
  expect(open).toHaveBeenCalledWith('run-private')
  expect(writes).toHaveLength(1)
  expect(writes[0]).toMatchObject({
    path: '/api/chat/conversations/current/turns',
    body: {
      mode: 'scan_email',
      credential_id: '',
      model: '',
      scan: { mailbox_id: 'mailbox', query: 'receipt', max_messages: 5 },
    },
  })
  const scope = writes[0].body.scan as { until_timestamp: number }
  expect(scope.until_timestamp).toBeGreaterThanOrEqual(before)
  expect(scope.until_timestamp).toBeLessThanOrEqual(
    Math.floor(Date.now() / 1000),
  )
  expect(screen.getByLabelText('Email scan mailbox')).toHaveValue('')
  expect(
    screen.getByRole('button', { name: 'Start email scan' }),
  ).toBeDisabled()
})

it('freezes the exact scope across a lost response and preserves the unsent note', async () => {
  const { writes } = harness(true)
  render(<ChatPanel csrfToken="csrf" />)
  const user = userEvent.setup()
  await user.click(
    await screen.findByRole('button', { name: 'Current conversation' }),
  )
  await user.type(screen.getByLabelText('Memory to save'), 'Keep my draft.')
  await user.selectOptions(screen.getByLabelText('Action'), 'scan_email')
  await screen.findByRole('option', { name: 'synthetic@example.test' })
  await user.selectOptions(
    screen.getByLabelText('Email scan mailbox'),
    'mailbox',
  )
  await user.click(screen.getByRole('button', { name: 'Start email scan' }))
  const retry = await screen.findByRole('button', {
    name: 'Retry same request',
  })
  expect(screen.getByLabelText('Email scan mailbox')).toBeDisabled()
  expect(screen.getByLabelText('Action')).toBeDisabled()
  await user.click(retry)
  await screen.findByText('Email scan queued.')
  expect(writes).toHaveLength(2)
  expect(writes[1]).toEqual(writes[0])
  await user.selectOptions(screen.getByLabelText('Action'), 'save')
  expect(screen.getByLabelText('Memory to save')).toHaveValue('Keep my draft.')
})

it('rejects out-of-range counts and dates without enqueueing', async () => {
  harness()
  const change = vi.fn()
  render(<ChatEmailScan disabled={false} onChange={change} />)
  const user = userEvent.setup()
  await screen.findByRole('option', { name: 'synthetic@example.test' })
  expect(change).toHaveBeenLastCalledWith(null)
  await user.selectOptions(
    screen.getByLabelText('Email scan mailbox'),
    'mailbox',
  )
  await waitFor(() =>
    expect(change.mock.lastCall?.[0]).toMatchObject({ mailbox_id: 'mailbox' }),
  )
  fireEvent.change(screen.getByLabelText('Maximum messages'), {
    target: { value: '51' },
  })
  expect(change).toHaveBeenLastCalledWith(null)
  fireEvent.change(screen.getByLabelText('Maximum messages'), {
    target: { value: '1' },
  })
  fireEvent.change(screen.getByLabelText('Scan from (UTC)'), {
    target: { value: '2020-01-01' },
  })
  expect(change).toHaveBeenLastCalledWith(null)
  expect(screen.getByRole('alert')).toHaveTextContent('at most 31 days')
})

it('reports mailbox metadata failures without making a write', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => json({}, 503)),
  )
  const change = vi.fn()
  render(<ChatEmailScan disabled={false} onChange={change} />)
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Unable to load connected mailboxes',
  )
  expect(change).toHaveBeenLastCalledWith(null)
})

it('clears the selected mailbox after changing action or starting a new conversation', async () => {
  const { writes } = harness()
  render(<ChatPanel csrfToken="csrf" />)
  const user = await chooseScan()
  expect(screen.getByRole('button', { name: 'Start email scan' })).toBeEnabled()
  await user.selectOptions(screen.getByLabelText('Action'), 'save')
  await user.selectOptions(screen.getByLabelText('Action'), 'scan_email')
  await screen.findByRole('option', { name: 'synthetic@example.test' })
  expect(screen.getByLabelText('Email scan mailbox')).toHaveValue('')
  expect(
    screen.getByRole('button', { name: 'Start email scan' }),
  ).toBeDisabled()
  await user.selectOptions(
    screen.getByLabelText('Email scan mailbox'),
    'mailbox',
  )
  await user.click(screen.getByRole('button', { name: 'New conversation' }))
  await screen.findByRole('option', { name: 'synthetic@example.test' })
  expect(screen.getByLabelText('Email scan mailbox')).toHaveValue('')
  expect(writes).toEqual([])
})

it('retains an uncertain first scan while its new conversation receives an id', async () => {
  const { writes } = harness(true)
  render(<ChatPanel csrfToken="csrf" />)
  const user = await chooseScan()
  await user.click(screen.getByRole('button', { name: 'New conversation' }))
  await screen.findByRole('option', { name: 'synthetic@example.test' })
  await user.selectOptions(
    screen.getByLabelText('Email scan mailbox'),
    'mailbox',
  )
  await user.click(screen.getByRole('button', { name: 'Start email scan' }))
  const retry = await screen.findByRole('button', {
    name: 'Retry same request',
  })
  expect(retry).toBeEnabled()
  expect(screen.getByLabelText('Email scan mailbox')).toHaveValue('mailbox')
  await user.click(retry)
  await screen.findByText('Email scan queued.')
  expect(writes).toHaveLength(2)
  expect(writes[0].path).toBe('/api/chat/conversations/new/turns')
  expect(writes[1]).toEqual(writes[0])
})
