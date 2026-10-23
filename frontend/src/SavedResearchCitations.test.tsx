import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import {
  SavedResearchCitations,
  type SavedResearchCitation,
} from './SavedResearchCitations'

const finding: SavedResearchCitation = {
  id: 'finding-1',
  citation: 1,
  asset_id: 'mower',
  asset_name: 'Garage mower',
  title: 'Synthetic manual',
  url: 'https://manufacturer.example/manual',
  published: '2025-04-01',
  researched_at: '2026-10-22T09:00:00Z',
  recorded_at: 1792660000000000,
  excerpt_kind: 'source',
  excerpts: ['Replace filter AB-12 every season.'],
}

it('shows dated saved source evidence and opens its asset separately from the page', async () => {
  const open = vi.fn()
  render(<SavedResearchCitations items={[finding]} onOpenAsset={open} />)
  expect(
    screen.getByRole('region', { name: 'Saved research inspected' }),
  ).toBeVisible()
  const link = screen.getByRole('link', {
    name: 'Research 1: Synthetic manual',
  })
  expect(link).toHaveAttribute('href', finding.url)
  expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  expect(screen.getByText(/Page dated 2025-04-01/)).toBeVisible()
  expect(screen.getByText(/Page dated 2025-04-01/)).toHaveTextContent(
    'Researched',
  )
  expect(screen.getByText('Saved source excerpts')).toBeVisible()
  expect(screen.getByText(finding.excerpts[0])).toBeVisible()
  expect(screen.getByText(/do not establish ownership/)).toBeVisible()
  await userEvent.click(
    screen.getByRole('button', { name: 'Open Garage mower saved research' }),
  )
  expect(open).toHaveBeenCalledWith('mower')
})

it('distinguishes generated answer excerpts, unknown dates and a limited selection', () => {
  render(
    <SavedResearchCitations
      items={[{ ...finding, excerpt_kind: 'answer', published: null }]}
      limited
    />,
  )
  expect(screen.getByText(/Saved generated answer excerpts/)).toBeVisible()
  expect(screen.queryByText('Saved source excerpts')).not.toBeInTheDocument()
  expect(screen.getByText(/Page date not reported/)).toBeVisible()
  expect(screen.getByText(/Other saved research may exist/)).toBeVisible()
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
})

it.each(['javascript:alert(1)', 'data:text/html,unsafe', '//unsafe.example'])(
  'does not link an unsafe stored URL: %s',
  (url) => {
    render(
      <SavedResearchCitations items={[{ ...finding, url, excerpts: [] }]} />,
    )
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText('Research 1: Synthetic manual')).toBeVisible()
    expect(screen.getByText(/No excerpts were saved/)).toBeVisible()
  },
)

it('explains an empty saved research selection', () => {
  render(<SavedResearchCitations items={[]} />)
  expect(screen.getByText(/No active saved findings were read/)).toBeVisible()
})
