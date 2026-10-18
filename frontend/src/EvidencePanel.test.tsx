import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { EvidencePanel, type EvidenceSource } from './EvidencePanel'
import { ChatRequestError } from './chatRequest'

const current: EvidenceSource = {
  id: 'note-original',
  text: 'My filter is 16x25x1.',
  note: {
    root_source_id: 'note-original',
    current_source_id: 'note-original',
    is_current: true,
    can_correct: true,
  },
}

it.each([
  [
    { ownership_statement_current_version: false },
    'This ownership statement has been superseded.',
  ],
  [
    { replacement_statement_current_version: false },
    'The linked replacement statement has been superseded or withdrawn.',
  ],
  [
    { association_versions_current: 1, association_versions_total: 2 },
    'Only 1 of 2 recorded association versions remain current.',
  ],
])(
  'labels historical correction evidence with its current version state',
  (state, message) => {
    render(
      <EvidencePanel
        source={{
          id: 'historical-correction',
          text: 'Exact earlier explanation.',
          asset_context: {
            asset_name: 'Original item',
            operation: 'reassociate',
            user_selected_status: null,
            ...state,
          },
        }}
        nextOffset={null}
        opening={false}
        onOpen={vi.fn()}
        onClose={vi.fn()}
        request={vi.fn()}
      />,
    )
    expect(screen.getByText(message, { exact: false })).toBeVisible()
    expect(screen.getByText('Exact earlier explanation.')).toBeVisible()
  },
)

it('names both items when inspecting a sourced reassociation correction', () => {
  render(
    <EvidencePanel
      source={{
        id: 'move-source',
        text: 'Exact correction explanation.',
        asset_context: {
          asset_name: 'Original drill',
          operation: 'reassociate',
          user_selected_status: null,
          target_asset_name: 'Replacement drill',
        },
      }}
      nextOffset={null}
      opening={false}
      onOpen={vi.fn()}
      onClose={vi.fn()}
      request={vi.fn()}
    />,
  )
  expect(screen.getByText('Receiving item: Replacement drill.')).toBeVisible()
  expect(screen.getByText(/Recorded against Original drill/)).toBeVisible()
})

describe('saved note correction and history', () => {
  it('submits a correction and opens its new source without rewriting original text', async () => {
    const user = userEvent.setup()
    const request = vi.fn().mockResolvedValue({ source: { id: 'corrected' } })
    const open = vi.fn().mockResolvedValue(undefined)
    render(
      <EvidencePanel
        source={current}
        nextOffset={null}
        opening={false}
        onOpen={open}
        onClose={() => {}}
        request={request}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Correct note' }))
    expect(
      screen.getByRole('button', { name: 'Save correction' }),
    ).toBeDisabled()
    await user.clear(screen.getByLabelText('Corrected note'))
    await user.type(
      screen.getByLabelText('Corrected note'),
      'My filter is 20x25x1.',
    )
    await user.click(screen.getByRole('button', { name: 'Save correction' }))
    expect(open).toHaveBeenCalledWith('corrected')
    const [path, init] = request.mock.calls[0]
    expect(path).toBe('/sources/note-original/corrections')
    expect(JSON.parse(init.body)).toMatchObject({
      text: 'My filter is 20x25x1.',
      request_id: expect.any(String),
    })
    expect(screen.getByText(current.text)).toBeVisible()
  })

  it('marks superseded evidence and pages history with safely rendered text', async () => {
    const user = userEvent.setup()
    const source = {
      ...current,
      note: {
        ...current.note!,
        current_source_id: 'newest',
        is_current: false,
        can_correct: false,
      },
    }
    const request = vi
      .fn()
      .mockResolvedValueOnce({
        items: [
          {
            id: 'note-original',
            text: '<script>old text</script>',
            recorded_at: 1000000,
            is_current: false,
            is_original: true,
          },
        ],
        next_cursor: 'cursor-1',
      })
      .mockResolvedValueOnce({
        items: [
          {
            id: 'newest',
            text: 'Current filter note',
            recorded_at: 2000000,
            is_current: true,
            is_original: false,
          },
        ],
        next_cursor: null,
      })
    const open = vi.fn().mockResolvedValue(undefined)
    render(
      <EvidencePanel
        source={source}
        nextOffset={null}
        opening={false}
        onOpen={open}
        onClose={() => {}}
        request={request}
      />,
    )
    expect(
      screen.queryByRole('button', { name: 'Correct note' }),
    ).not.toBeInTheDocument()
    expect(screen.getByText(/Earlier version/)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'View current note' }))
    expect(open).toHaveBeenCalledWith('newest')
    await user.click(screen.getByRole('button', { name: 'View note history' }))
    expect(await screen.findByText(/<script>old text<\/script>/)).toBeVisible()
    expect(document.querySelector('script')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'More note history' }))
    expect(await screen.findByText(/Current filter note/)).toBeVisible()
    expect(request.mock.calls[1][0]).toBe(
      '/sources/note-original/history?cursor=cursor-1',
    )
  })

  it('retries a lost correction response with exactly the same request', async () => {
    const user = userEvent.setup()
    const request = vi
      .fn()
      .mockRejectedValueOnce(new Error('network lost'))
      .mockResolvedValueOnce({ source: { id: 'corrected' } })
    render(
      <EvidencePanel
        source={current}
        nextOffset={null}
        opening={false}
        onOpen={vi.fn()}
        onClose={() => {}}
        request={request}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Correct note' }))
    await user.clear(screen.getByLabelText('Corrected note'))
    await user.type(
      screen.getByLabelText('Corrected note'),
      'My filter is 20x25x1.',
    )
    await user.click(screen.getByRole('button', { name: 'Save correction' }))
    await screen.findByRole('alert')
    expect(screen.getByLabelText('Corrected note')).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Retry correction' }))
    expect(request.mock.calls[0][1].body).toBe(request.mock.calls[1][1].body)
  })

  it('does not retry a stale edit and reloads the original source metadata', async () => {
    const user = userEvent.setup()
    const request = vi
      .fn()
      .mockRejectedValue(new ChatRequestError('Conflict', 409))
    const open = vi.fn().mockResolvedValue(undefined)
    render(
      <EvidencePanel
        source={current}
        nextOffset={null}
        opening={false}
        onOpen={open}
        onClose={() => {}}
        request={request}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Correct note' }))
    await user.type(screen.getByLabelText('Corrected note'), ' A correction.')
    await user.click(screen.getByRole('button', { name: 'Save correction' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'changed in another request',
    )
    expect(open).toHaveBeenCalledWith('note-original')
    expect(screen.queryByLabelText('Corrected note')).not.toBeInTheDocument()
    expect(request).toHaveBeenCalledTimes(1)
  })
})
