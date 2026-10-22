import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { FactStatus } from './FactStatus'

it.each([
  ['stated', 'Stated in saved evidence'],
  ['inferred', 'Inferred; not confirmed by you'],
  ['unknown', 'Not known'],
])('labels a %s statement distinctly', (status, hint) => {
  render(<FactStatus status={status} />)
  const badge = screen.getByText(status, { exact: true })
  expect(badge).toHaveAttribute('data-status', status)
  expect(badge).toHaveAttribute('title', hint)
})

it('shows an unlisted status without a hint', () => {
  render(<FactStatus status="disputed" />)
  expect(screen.getByText('disputed')).not.toHaveAttribute('title')
})
