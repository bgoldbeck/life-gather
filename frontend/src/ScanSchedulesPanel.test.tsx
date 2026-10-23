import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ScanSchedulesPanel } from './ScanSchedulesPanel'

afterEach(() => vi.unstubAllGlobals())

it('schedules discovery using the chosen AI adapter without changing evidence-only defaults', async () => {
  const user = userEvent.setup()
  let saved: unknown
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        saved = JSON.parse(String(init.body))
        return new Response('{}')
      }
      return new Response(
        JSON.stringify(
          url.includes('credentials')
            ? {
                items: [
                  {
                    id: 'claude',
                    kind: 'ai',
                    provider: 'anthropic',
                    label: 'Synthetic Claude',
                  },
                ],
              }
            : url.endsWith('settings')
              ? { allow_external_ai: true }
              : { items: [] },
        ),
      )
    }),
  )
  render(
    <ScanSchedulesPanel
      csrfToken="csrf"
      mailboxes={[{ id: 'mailbox', address: 'synthetic@example.test' }]}
      onRun={vi.fn()}
    />,
  )
  await screen.findByRole('button', { name: /^Create schedule$/ })
  await user.type(screen.getByLabelText('Schedule name'), 'Discover receipts')
  await user.selectOptions(
    screen.getByLabelText('Scheduled scan type'),
    'gmail_discovery',
  )
  await screen.findByRole('option', { name: 'Synthetic Claude (anthropic)' })
  await user.selectOptions(
    screen.getByLabelText('Discovery AI connection'),
    'claude',
  )
  await user.type(screen.getByLabelText('Discovery model'), 'synthetic-model')
  await user.click(screen.getByRole('button', { name: /^Create schedule$/ }))
  await waitFor(() =>
    expect(saved).toMatchObject({
      handler_key: 'gmail_discovery',
      config: {
        mailbox_id: 'mailbox',
        credential_id: 'claude',
        model: 'synthetic-model',
      },
    }),
  )
})

it('schedules attachment imports with the tighter message limit', async () => {
  const user = userEvent.setup()
  let saved: unknown
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        saved = JSON.parse(String(init.body))
        return new Response('{}')
      }
      return new Response('{"items":[]}')
    }),
  )
  render(
    <ScanSchedulesPanel
      csrfToken="csrf"
      mailboxes={[{ id: 'mailbox', address: 'synthetic@example.test' }]}
      onRun={vi.fn()}
    />,
  )
  await screen.findByRole('button', { name: /^Create schedule$/ })
  await user.type(screen.getByLabelText('Schedule name'), 'Emailed photos')
  await user.selectOptions(
    screen.getByLabelText('Scheduled scan type'),
    'gmail_attachments',
  )
  expect(screen.getByText(/JPEG, PNG and WebP photos/)).toBeVisible()
  const limit = screen.getByLabelText('Scheduled maximum messages')
  expect(limit).toHaveValue(10)
  expect(limit).toHaveAttribute('max', '20')
  expect(screen.queryByLabelText('Discovery model')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /^Create schedule$/ }))
  await waitFor(() =>
    expect(saved).toMatchObject({
      handler_key: 'gmail_attachments',
      config: { mailbox_id: 'mailbox', query: '', max_messages: 10 },
    }),
  )
  expect((saved as { config: object }).config).not.toHaveProperty('model')
})

it('creates only after explicit submission and supports a private pause action', async () => {
  const user = userEvent.setup()
  let saved: unknown[] = []
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      if (init?.method === 'POST') {
        saved = [
          {
            id: 'schedule',
            label: 'Daily receipts',
            handler_key: 'gmail_import',
            cadence: 'daily',
            timezone: 'UTC',
            local_time: '09:00',
            weekday: 0,
            lookback_days: 7,
            enabled: !url.includes('toggle'),
            revision: 1,
            next_run: 1770000000,
            last_status: url.includes('toggle') ? 'paused' : 'scheduled',
            scope: { mailbox_id: 'mailbox', query: '', max_messages: 20 },
          },
        ]
        return new Response(JSON.stringify(saved[0]))
      }
      return new Response(JSON.stringify({ items: saved }))
    }),
  )
  render(
    <ScanSchedulesPanel
      csrfToken="csrf"
      mailboxes={[{ id: 'mailbox', address: 'synthetic@example.test' }]}
      onRun={() => undefined}
    />,
  )
  await screen.findByRole('button', { name: /^Create schedule$/ })
  expect(calls.filter((call) => call.init?.method === 'POST')).toHaveLength(0)
  await user.type(screen.getByLabelText('Schedule name'), 'Daily receipts')
  await user.click(screen.getByRole('button', { name: /^Create schedule$/ }))
  const pause = await screen.findByRole('button', {
    name: /^Pause Daily receipts$/,
  })
  await user.click(pause)
  await waitFor(() =>
    expect(calls.filter((call) => call.init?.method === 'POST')).toHaveLength(
      2,
    ),
  )
  const create = calls.find((call) => call.init?.method === 'POST')!
  const body = JSON.parse(String(create.init?.body))
  expect(body.handler_key).toBe('gmail_import')
  expect(body.config.mailbox_id).toBe('mailbox')
  expect(body.request_id).toBeTruthy()
  expect(create.init?.headers).toMatchObject({ 'X-CSRF-Token': 'csrf' })
})

it('undoes a pause with the revision the pause returned', async () => {
  const user = userEvent.setup()
  const toggles: unknown[] = []
  let current = {
    id: 'schedule',
    label: 'Daily receipts',
    handler_key: 'gmail_import',
    cadence: 'daily',
    timezone: 'UTC',
    local_time: '09:00',
    weekday: 0,
    lookback_days: 7,
    enabled: true,
    revision: 3,
    next_run: 1770000000,
    last_status: 'scheduled',
    scope: { mailbox_id: 'mailbox', query: '', max_messages: 20 },
  }
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/toggle')) {
        const body = JSON.parse(String(init?.body))
        toggles.push(body)
        current = {
          ...current,
          enabled: body.enabled,
          revision: current.revision + 1,
          last_status: body.enabled ? 'scheduled' : 'paused',
        }
        return new Response(JSON.stringify(current))
      }
      return new Response(JSON.stringify({ items: [current] }))
    }),
  )
  render(
    <ScanSchedulesPanel
      csrfToken="csrf"
      mailboxes={[{ id: 'mailbox', address: 'synthetic@example.test' }]}
      onRun={() => undefined}
    />,
  )
  await user.click(
    await screen.findByRole('button', { name: /^Pause Daily receipts$/ }),
  )
  await user.click(await screen.findByRole('button', { name: 'Undo pause' }))
  await screen.findByText(/Pause undone/)
  expect(toggles).toEqual([
    { expected_revision: 3, enabled: false },
    { expected_revision: 4, enabled: true },
  ])
  expect(
    await screen.findByRole('button', { name: /^Pause Daily receipts$/ }),
  ).toBeVisible()
})

it('edits a paused schedule using its revision and opens the saved run', async () => {
  const user = userEvent.setup()
  const onRun = vi.fn()
  const writes: { url: string; init?: RequestInit }[] = []
  const saved = {
    id: 'existing',
    label: 'Weekly receipts',
    handler_key: 'gmail_import',
    timezone: 'UTC',
    cadence: 'weekly',
    weekday: 2,
    local_time: '10:30',
    lookback_days: 7,
    enabled: false,
    revision: 7,
    next_run: 1770000000,
    last_run_id: 'run',
    last_status: 'paused',
    scope: { mailbox_id: 'mailbox', query: 'receipt', max_messages: 15 },
  }
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        writes.push({ url, init })
        return new Response(JSON.stringify({ ...saved, revision: 8 }))
      }
      return new Response(JSON.stringify({ items: [saved] }))
    }),
  )
  render(
    <ScanSchedulesPanel
      csrfToken="csrf"
      mailboxes={[{ id: 'mailbox', address: 'synthetic@example.test' }]}
      onRun={onRun}
    />,
  )
  await user.click(
    await screen.findByRole('button', { name: /^Edit Weekly receipts$/ }),
  )
  expect(screen.getByLabelText('Frequency')).toHaveValue('weekly')
  expect(screen.getByLabelText('Day of week')).toHaveValue('2')
  await user.clear(screen.getByLabelText('Local run time'))
  await user.type(screen.getByLabelText('Local run time'), '11:15')
  await user.click(screen.getByRole('button', { name: /^Save schedule$/ }))
  await waitFor(() => expect(writes).toHaveLength(1))
  expect(writes[0].url).toBe('/api/scan-schedules/existing/edit')
  const body = JSON.parse(String(writes[0].init?.body))
  expect(body.expected_revision).toBe(7)
  expect(body.data.config).toEqual({
    mailbox_id: 'mailbox',
    query: 'receipt',
    max_messages: 15,
  })
  expect(body.data.local_time).toBe('11:15')
  await user.click(
    screen.getByRole('button', { name: /^View last run for Weekly receipts$/ }),
  )
  expect(onRun).toHaveBeenCalledWith('run')
})

it('retries an unconfirmed create with an identical request identity', async () => {
  const user = userEvent.setup()
  const writes: RequestInit[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        writes.push(init)
        if (writes.length === 1) throw new Error('Lost response')
        return new Response('{}')
      }
      return new Response('{"items":[]}')
    }),
  )
  render(
    <ScanSchedulesPanel
      csrfToken="csrf"
      mailboxes={[{ id: 'mailbox', address: 'synthetic@example.test' }]}
      onRun={() => undefined}
    />,
  )
  await user.type(screen.getByLabelText('Schedule name'), 'Synthetic schedule')
  await user.click(screen.getByRole('button', { name: /^Create schedule$/ }))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('Schedule name')).toBeDisabled()
  await user.click(
    screen.getByRole('button', { name: /^Retry schedule save$/ }),
  )
  await waitFor(() => expect(writes).toHaveLength(2))
  expect(writes[0].body).toEqual(writes[1].body)
})
