import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { AssetConsolidation } from './AssetConsolidation'

afterEach(() => vi.unstubAllGlobals())
const records = [
  { id: 'first', name: 'Manual mower' },
  { id: 'second', name: 'Receipt mower' },
]
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status })
const comparison = {
  complete: true,
  records,
  counts: { statements: 2, photos: 1 },
  limited_sections: [],
  warnings: [],
  sections: {},
}
const result = {
  id: 'choice',
  primary_id: 'first',
  secondary_id: 'second',
  source_id: 'explanation',
  recorded_at: 100,
}

it('requires fresh preview, primary choice, explanation and explicit confirmation', async () => {
  const user = userEvent.setup()
  const changed = vi.fn(async () => {})
  const previewed = vi.fn()
  const fetcher = vi.fn(async (path: string, _init?: RequestInit) =>
    path.endsWith('/preview')
      ? json({ comparison, preview_token: 'a'.repeat(64) })
      : json(result),
  )
  vi.stubGlobal('fetch', fetcher)
  render(
    <AssetConsolidation
      records={records}
      csrfToken="csrf"
      onPreview={previewed}
      onChanged={changed}
    />,
  )
  expect(
    screen.getByRole('button', { name: 'Confirm consolidation' }),
  ).toBeDisabled()
  await user.click(
    screen.getByRole('button', { name: 'Preview consolidation' }),
  )
  expect(previewed).toHaveBeenCalledWith(comparison)
  await user.type(screen.getByLabelText('Explanation'), 'Same physical mower.')
  expect(
    screen.getByRole('button', { name: 'Confirm consolidation' }),
  ).toBeDisabled()
  await user.click(screen.getByRole('checkbox'))
  await user.click(
    screen.getByRole('button', { name: 'Confirm consolidation' }),
  )
  expect(changed).toHaveBeenCalledWith('first')
  const init = fetcher.mock.calls[1][1] as RequestInit
  expect(init.headers).toMatchObject({ 'X-CSRF-Token': 'csrf' })
  expect(JSON.parse(init.body as string)).toMatchObject({
    primary_id: 'first',
    secondary_id: 'second',
    same_item_confirmed: true,
    note: 'Same physical mower.',
  })
})

it('invalidates preview when primary changes and refuses incomplete previews', async () => {
  const user = userEvent.setup()
  const fetcher = vi.fn(async () =>
    json({ comparison, preview_token: 'a'.repeat(64) }),
  )
  vi.stubGlobal('fetch', fetcher)
  render(
    <AssetConsolidation
      records={records}
      csrfToken="c"
      onChanged={async () => {}}
    />,
  )
  await user.click(
    screen.getByRole('button', { name: 'Preview consolidation' }),
  )
  await user.type(screen.getByLabelText('Explanation'), 'Same item.')
  await user.click(screen.getByRole('checkbox'))
  expect(
    screen.getByRole('button', { name: 'Confirm consolidation' }),
  ).toBeEnabled()
  await user.selectOptions(screen.getByLabelText('Primary record'), 'second')
  expect(
    screen.getByRole('button', { name: 'Confirm consolidation' }),
  ).toBeDisabled()
  fetcher.mockImplementation(async () =>
    json({
      comparison: { ...comparison, complete: false },
      preview_token: 'a'.repeat(64),
    }),
  )
  await user.click(
    screen.getByRole('button', { name: 'Preview consolidation' }),
  )
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'complete current preview',
  )
})

it('freezes uncertain writes and retries the identical request after a lost response', async () => {
  const user = userEvent.setup()
  const bodies: string[] = []
  const fetcher = vi.fn(async (path: string, init: RequestInit) => {
    if (path.endsWith('/preview'))
      return json({ comparison, preview_token: 'a'.repeat(64) })
    bodies.push(init.body as string)
    if (bodies.length === 1) throw new Error('Lost response')
    return json(result)
  })
  vi.stubGlobal('fetch', fetcher)
  const changed = vi.fn(async () => {})
  render(
    <AssetConsolidation records={records} csrfToken="c" onChanged={changed} />,
  )
  await user.click(
    screen.getByRole('button', { name: 'Preview consolidation' }),
  )
  await user.type(screen.getByLabelText('Explanation'), 'Same item.')
  await user.click(screen.getByRole('checkbox'))
  await user.click(
    screen.getByRole('button', { name: 'Confirm consolidation' }),
  )
  expect(screen.getByLabelText('Explanation')).toBeDisabled()
  expect(screen.getByLabelText('Primary record')).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Retry same request' }))
  expect(bodies).toHaveLength(2)
  expect(bodies[0]).toBe(bodies[1])
  expect(changed).toHaveBeenCalledTimes(1)
})

it('keeps saved writes separate from reload failure and supports explicit reversal', async () => {
  const user = userEvent.setup()
  const changed = vi.fn(async () => {
    throw new Error('Reload failed')
  })
  const fetcher = vi.fn(async () => json({ ...result, operation: 'reverse' }))
  vi.stubGlobal('fetch', fetcher)
  render(
    <AssetConsolidation
      consolidation={result}
      csrfToken="c"
      onChanged={changed}
    />,
  )
  await user.type(screen.getByLabelText('Explanation'), 'Mistaken match.')
  await user.click(screen.getByRole('checkbox'))
  await user.click(
    screen.getByRole('button', { name: 'Reverse consolidation' }),
  )
  expect(await screen.findByRole('alert')).toHaveTextContent('change is saved')
  await user.click(screen.getByRole('button', { name: 'Reload record' }))
  expect(fetcher).toHaveBeenCalledTimes(1)
  expect(changed).toHaveBeenCalledTimes(2)
})

it('discards a late preview after unmount and requires another preview after conflict', async () => {
  const user = userEvent.setup()
  let release!: (value: Response) => void
  const fetcher = vi.fn(
    () =>
      new Promise<Response>((resolve) => {
        release = resolve
      }),
  )
  vi.stubGlobal('fetch', fetcher)
  const previewed = vi.fn()
  const view = render(
    <AssetConsolidation
      records={records}
      csrfToken="c"
      onPreview={previewed}
      onChanged={async () => {}}
    />,
  )
  await user.click(
    screen.getByRole('button', { name: 'Preview consolidation' }),
  )
  view.unmount()
  await act(async () =>
    release(json({ comparison, preview_token: 'a'.repeat(64) })),
  )
  expect(previewed).not.toHaveBeenCalled()
})
