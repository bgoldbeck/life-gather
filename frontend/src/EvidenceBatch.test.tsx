import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { EvidenceBatch } from './EvidenceBatch'

afterEach(() => vi.unstubAllGlobals())

const preview = {
  preview_token: 'a'.repeat(64),
  asset_name: 'Original drill',
  target_asset_name: 'Destination drill',
  entries: [
    {
      decision_id: 'decision-one',
      source_id: 'source-one',
      name: 'Drill',
      quote: 'Exact receipt text',
      unit: 1,
      quantity: 2,
    },
    {
      decision_id: 'decision-two',
      source_id: 'source-two',
      name: 'Drill',
      quote: 'Exact shipping text',
      unit: 1,
      quantity: 1,
      quote_truncated: true,
    },
  ],
}

function fixture({
  loseResponse = false,
  restoreId,
  reject = false,
  reloadFailure = false,
}: {
  loseResponse?: boolean
  restoreId?: string
  reject?: boolean
  reloadFailure?: boolean
} = {}) {
  const writes: { path: string; body: Record<string, unknown> }[] = []
  const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.startsWith('/api/assets?'))
      return new Response(
        JSON.stringify({
          items: [{ id: 'target', name: 'Destination drill' }],
          next_cursor: null,
        }),
      )
    if (path.endsWith('/preview')) return new Response(JSON.stringify(preview))
    writes.push({ path, body: JSON.parse(String(init?.body)) })
    if (loseResponse && writes.length === 1)
      throw new Error('Synthetic lost response')
    return new Response(JSON.stringify({ id: 'saved' }), {
      status: reject ? 409 : 200,
    })
  })
  vi.stubGlobal('fetch', fetcher)
  const changed = reloadFailure
    ? vi
        .fn()
        .mockRejectedValueOnce(new Error('Synthetic reload failure'))
        .mockResolvedValue(undefined)
    : vi.fn().mockResolvedValue(undefined)
  const open = vi.fn().mockResolvedValue(undefined)
  render(
    <EvidenceBatch
      assetId="original"
      assetName="Original drill"
      csrfToken="csrf"
      restoreId={restoreId}
      onChanged={changed}
      onOpen={open}
    />,
  )
  return { user: userEvent.setup(), fetcher, writes, changed, open }
}

async function chooseAndPreview(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Find destinations' }))
  await user.selectOptions(screen.getByLabelText('Destination item'), 'target')
  await user.click(
    screen.getByRole('button', { name: 'Preview evidence move' }),
  )
  await screen.findByRole('region', { name: 'Evidence move preview' })
}

it('previews every source and unit before moving exactly that batch', async () => {
  const { user, writes, open, changed } = fixture()
  expect(
    screen.getByRole('button', { name: 'Move previewed evidence' }),
  ).toBeDisabled()
  await chooseAndPreview(user)
  expect(screen.getByText('Exact receipt text')).toBeInTheDocument()
  expect(screen.getByText(/unit 1 of 2/)).toBeInTheDocument()
  expect(screen.getByText(/Passage shortened/)).toBeInTheDocument()
  await user.click(
    screen.getAllByRole('button', { name: 'Open batch source' })[1]!,
  )
  expect(open).toHaveBeenCalledWith('source-two')
  expect(writes).toHaveLength(0)
  await user.type(
    screen.getByLabelText('Explanation for this batch'),
    'These sources describe the same physical drill.',
  )
  await user.click(
    screen.getByRole('button', { name: 'Move previewed evidence' }),
  )
  expect(writes).toHaveLength(1)
  expect(writes[0]?.body).toMatchObject({
    asset_id: 'original',
    target_asset_id: 'target',
    preview_token: preview.preview_token,
    note: 'These sources describe the same physical drill.',
  })
  expect(changed).toHaveBeenCalledTimes(1)
})

it('keeps an identical request and freezes inputs after a lost response', async () => {
  const { user, writes, changed } = fixture({ loseResponse: true })
  await chooseAndPreview(user)
  await user.type(
    screen.getByLabelText('Explanation for this batch'),
    'Move reviewed sources.',
  )
  await user.click(
    screen.getByRole('button', { name: 'Move previewed evidence' }),
  )
  expect(await screen.findByRole('status')).toHaveTextContent('Connection lost')
  expect(screen.getByLabelText('Find destination item')).toBeDisabled()
  expect(screen.getByLabelText('Explanation for this batch')).toBeDisabled()
  await user.click(
    screen.getByRole('button', { name: 'Retry same evidence batch' }),
  )
  expect(writes).toHaveLength(2)
  expect(writes[0]).toEqual(writes[1])
  expect(changed).toHaveBeenCalledTimes(1)
})

it('invalidates the preview when the destination search changes', async () => {
  const { user, writes } = fixture()
  await chooseAndPreview(user)
  await user.type(screen.getByLabelText('Find destination item'), 'another')
  expect(
    screen.queryByRole('region', { name: 'Evidence move preview' }),
  ).not.toBeInTheDocument()
  expect(screen.getByLabelText('Destination item')).toHaveValue('')
  expect(
    screen.getByRole('button', { name: 'Move previewed evidence' }),
  ).toBeDisabled()
  expect(writes).toHaveLength(0)
})

it('requires a new preview after a server refusal and keeps the explanation', async () => {
  const { user, writes } = fixture({ reject: true })
  await chooseAndPreview(user)
  await user.type(
    screen.getByLabelText('Explanation for this batch'),
    'Keep this explanation.',
  )
  await user.click(
    screen.getByRole('button', { name: 'Move previewed evidence' }),
  )
  expect(await screen.findByRole('status')).toHaveTextContent('refused')
  expect(screen.getByLabelText('Explanation for this batch')).toHaveValue(
    'Keep this explanation.',
  )
  expect(
    screen.queryByRole('region', { name: 'Evidence move preview' }),
  ).not.toBeInTheDocument()
  expect(
    screen.getByRole('button', { name: 'Move previewed evidence' }),
  ).toBeDisabled()
  expect(writes).toHaveLength(1)
})

it('reverses the recorded batch with an explanation and retries only its reload after success', async () => {
  const { user, writes, changed } = fixture({
    restoreId: 'batch-original',
    reloadFailure: true,
  })
  expect(
    screen.getByRole('button', { name: 'Reverse latest evidence batch' }),
  ).toBeDisabled()
  await user.type(
    screen.getByLabelText('Explanation for this batch'),
    'Restore the recorded mappings.',
  )
  await user.click(
    screen.getByRole('button', { name: 'Reverse latest evidence batch' }),
  )
  expect(writes[0]).toMatchObject({
    path: '/api/assets/evidence/restore',
    body: {
      action_id: 'batch-original',
      note: 'Restore the recorded mappings.',
    },
  })
  expect(await screen.findByRole('status')).toHaveTextContent('Change saved')
  expect(
    screen.getByRole('button', { name: 'Move previewed evidence' }),
  ).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Reload saved batch' }))
  expect(changed).toHaveBeenCalledTimes(2)
  expect(writes).toHaveLength(1)
})
