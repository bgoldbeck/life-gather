import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { DocumentsPanel } from './DocumentsPanel'

afterEach(() => vi.unstubAllGlobals())

it('uploads Word evidence and shows parser limitations without saving automatically', async () => {
  const fetcher = vi.fn(
    async (_path: string, init?: RequestInit) =>
      new Response(
        JSON.stringify(
          init?.method === 'POST'
            ? {
                id: 'word',
                filename: 'guide.docx',
                format: 'docx',
                size: 300,
                pages: 1,
                extracted_text: '[Paragraph 1] Filter 0012',
                text_truncated: false,
                extraction_metadata: { warnings: ['Main body only.'] },
                source_id: null,
                updated_at: 100,
                deleted_at: null,
              }
            : { items: [], next_cursor: null },
        ),
      ),
  )
  vi.stubGlobal('fetch', fetcher)
  render(<DocumentsPanel csrfToken="csrf" />)
  await userEvent.upload(
    screen.getByLabelText('Document file'),
    new File(['synthetic'], 'guide.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    }),
  )
  await userEvent.click(screen.getByRole('button', { name: 'Upload document' }))
  expect(await screen.findByLabelText('Reviewed text')).toHaveValue(
    '[Paragraph 1] Filter 0012',
  )
  expect(screen.getByText('Main body only.')).toBeVisible()
  expect(
    screen.getByRole('link', { name: 'Download original document' }),
  ).toHaveAttribute('href', '/api/documents/word/original')
  expect(
    fetcher.mock.calls.some(([path]) => path === '/api/documents/text'),
  ).toBe(false)
})

it('previews a selected Excel sheet and range before replacing the review draft', async () => {
  const doc = {
    id: 'sheet',
    filename: 'inventory.xlsx',
    format: 'xlsx',
    size: 300,
    pages: 1,
    extracted_text: '[Inventory!A1] Original',
    text_truncated: false,
    extraction_metadata: { sheets: ['Inventory', 'Other'], warnings: [] },
    source_id: null,
    updated_at: 100,
    deleted_at: null,
  }
  const fetcher = vi.fn(
    async (path: string, init?: RequestInit) =>
      new Response(
        JSON.stringify(
          path === '/api/documents/preview'
            ? {
                text: '[Other!A1] Selected',
                truncated: false,
                metadata: { warnings: [] },
              }
            : init?.method === 'POST'
              ? doc
              : { items: [], next_cursor: null },
        ),
      ),
  )
  vi.stubGlobal('fetch', fetcher)
  render(<DocumentsPanel csrfToken="csrf" />)
  await userEvent.upload(
    screen.getByLabelText('Document file'),
    new File(['synthetic'], 'inventory.xlsx'),
  )
  await userEvent.click(screen.getByRole('button', { name: 'Upload document' }))
  await screen.findByLabelText('Reviewed text')
  await userEvent.selectOptions(screen.getByLabelText('Worksheet'), 'Other')
  await userEvent.type(screen.getByLabelText('Cell range'), 'A1:A1')
  await userEvent.click(
    screen.getByRole('button', { name: 'Preview selection' }),
  )
  expect(await screen.findByText('[Other!A1] Selected')).toBeVisible()
  expect(screen.getByLabelText('Reviewed text')).toHaveValue(
    '[Inventory!A1] Original',
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Use preview as reviewed text' }),
  )
  expect(screen.getByLabelText('Reviewed text')).toHaveValue(
    '[Other!A1] Selected',
  )
})

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
    screen.getByLabelText('Document file'),
    new File(['%PDF-synthetic'], 'synthetic.pdf', { type: 'application/pdf' }),
  )
  await userEvent.click(screen.getByRole('button', { name: 'Upload document' }))
  expect(await screen.findByLabelText('Reviewed text')).toHaveValue(
    'Synthetic receipt',
  )
  expect(
    fetcher.mock.calls.some(([path]) => path === '/api/documents/text'),
  ).toBe(false)
  expect(
    screen.getByRole('link', { name: 'Download original document' }),
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
