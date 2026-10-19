import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { FieldHistory } from './FieldHistory'

afterEach(() => vi.unstubAllGlobals())
const version = {
  id: 'first',
  value: 'Blue',
  object_id: null,
  status: 'stated',
  recorded_at: 1792348800000000,
  valid_from: null,
  valid_to: null,
  superseded_at: null,
  previous: null,
  origin: null,
  more_evidence: false,
  evidence: [
    {
      source_id: 'source',
      quote: '<script>untrusted()</script>',
      source_type: 'manual',
      source_origin: null,
      quote_truncated: true,
    },
  ],
}
it('explicitly loads provenance, follows pages and retries without losing history', async () => {
  const user = userEvent.setup()
  const open = vi.fn()
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ items: [version], next_cursor: 'first' })),
    )
    .mockResolvedValueOnce(new Response('', { status: 500 }))
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          items: [
            {
              ...version,
              id: 'second',
              value: 'Red',
              status: 'inferred',
              previous: version,
              origin: {
                method: 'ai_inference',
                interface: 'worker',
                initiator: 'scheduled',
                provider: 'openai',
                model: 'synthetic',
              },
            },
          ],
          next_cursor: null,
        }),
      ),
    )
  vi.stubGlobal('fetch', fetcher)
  render(<FieldHistory entityId="truck" field="paint" onOpenSource={open} />)
  expect(fetcher).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'View paint history' }))
  expect(await screen.findByText('Origin not recorded')).toBeVisible()
  expect(screen.getByText(/Statement status: stated/)).toBeVisible()
  expect(
    screen.getByText('<script>untrusted()</script>… (excerpt shortened)'),
  ).toBeVisible()
  await user.click(
    screen.getByRole('button', { name: 'Open history evidence 1' }),
  )
  expect(open).toHaveBeenCalledWith('source')
  await user.click(screen.getByRole('button', { name: 'More field changes' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Try again')
  expect(screen.getByText('"Blue"')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'More field changes' }))
  expect(await screen.findByText('"Blue" → "Red"')).toBeVisible()
  expect(
    screen.getByText(/ai inference · worker · scheduled · openai · synthetic/),
  ).toBeVisible()
  expect(fetcher.mock.calls[2][0]).toContain('cursor=first')
  expect(fetcher.mock.calls[0][1].cache).toBe('no-store')
})
it('cancels old record reads and ignores late responses after context changes', async () => {
  const user = userEvent.setup()
  let finish: (response: Response) => void = () => {}
  const fetcher = vi
    .fn()
    .mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve
        }),
    )
    .mockResolvedValue(
      new Response(JSON.stringify({ items: [], next_cursor: null })),
    )
  vi.stubGlobal('fetch', fetcher)
  const view = render(
    <FieldHistory entityId="old" field="paint" onOpenSource={vi.fn()} />,
  )
  await user.click(screen.getByRole('button', { name: 'View paint history' }))
  view.rerender(
    <FieldHistory entityId="new" field="paint" onOpenSource={vi.fn()} />,
  )
  expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true)
  await act(async () =>
    finish(
      new Response(JSON.stringify({ items: [version], next_cursor: null })),
    ),
  )
  expect(screen.queryByText('"Blue"')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'View paint history' }))
  expect(
    await screen.findByText('No recorded versions for this field.'),
  ).toBeVisible()
  expect(fetcher.mock.calls[1][0]).toContain('entity_id=new')
})

it('reduces oversized pages while preserving the cursor and explicit source attribution', async () => {
  const user = userEvent.setup()
  const origin = {
    method: 'ai_extraction',
    interface: 'web',
    initiator: 'account_request',
    provider: 'openai',
    model: 'synthetic',
  }
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          detail:
            'Field history exceeds the response limit; request a smaller page',
        }),
        { status: 400 },
      ),
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          items: [{ ...version, proposal_origin: origin }],
          next_cursor: 'first',
        }),
      ),
    )
  vi.stubGlobal('fetch', fetcher)
  render(<FieldHistory entityId="truck" field="paint" onOpenSource={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: 'View paint history' }))
  expect(
    await screen.findByText(/Original suggestion: ai extraction/),
  ).toBeVisible()
  expect(fetcher.mock.calls[0][0]).toContain('limit=5')
  expect(fetcher.mock.calls[1][0]).toContain('limit=1')
})
