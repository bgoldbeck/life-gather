import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { DocumentsPanel } from './DocumentsPanel'

afterEach(() => vi.unstubAllGlobals())

it('uploads a private PDF and requires reviewed text before memory capture', async () => {
  const doc = {
    id: 'doc',
    filename: 'synthetic.pdf',
    size: 200,
    pages: 1,
    extracted_text: 'Synthetic receipt',
    text_truncated: false,
    source_id: null,
    updated_at: 100,
    deleted_at: null,
  }
  const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST' && path === '/api/documents/text')
      return new Response(
        JSON.stringify({ ...doc, source_id: 'source', updated_at: 101 }),
      )
    if (init?.method === 'POST') return new Response(JSON.stringify(doc))
    return new Response(JSON.stringify({ items: [], next_cursor: null }))
  })
  vi.stubGlobal('fetch', fetcher)
  render(<DocumentsPanel csrfToken="csrf" />)
  await userEvent.upload(
    screen.getByLabelText('PDF file'),
    new File(['%PDF-synthetic'], 'synthetic.pdf', { type: 'application/pdf' }),
  )
  await userEvent.click(screen.getByRole('button', { name: 'Upload PDF' }))
  expect(await screen.findByLabelText('Reviewed text')).toHaveValue(
    'Synthetic receipt',
  )
  expect(
    fetcher.mock.calls.some(([path]) => path === '/api/documents/text'),
  ).toBe(false)
  expect(
    screen.getByRole('link', { name: 'Download original PDF' }),
  ).toHaveAttribute('href', '/api/documents/doc/original')
  await userEvent.click(
    screen.getByRole('button', { name: 'Save reviewed text to memory' }),
  )
  expect(
    await screen.findByText('Reviewed text saved. No assets were created.'),
  ).toBeVisible()
  const [, init] = fetcher.mock.calls.find(
    ([path]) => path === '/api/documents/text',
  )!
  expect(JSON.parse(String(init?.body))).toMatchObject({
    document_id: 'doc',
    text: 'Synthetic receipt',
    expected_updated_at: 100,
  })
})
