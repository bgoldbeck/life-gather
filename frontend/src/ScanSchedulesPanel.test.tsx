import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ScanSchedulesPanel } from './ScanSchedulesPanel'

afterEach(() => vi.unstubAllGlobals())

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
