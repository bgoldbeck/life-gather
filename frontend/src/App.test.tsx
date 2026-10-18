import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { Workspace as App } from './App'

describe('LifeGather shell', () => {
  it('shows the planned navigation and an honest empty overview', () => {
    render(<App />)
    const navigation = screen.getByRole('navigation', {
      name: 'Main navigation',
    })
    for (const name of [
      'Chat',
      'Overview',
      'Assets',
      'Memories',
      'Graph',
      'Settings',
    ]) {
      expect(within(navigation).getByRole('button', { name })).toBeVisible()
    }
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'A little less to remember.',
    )
    expect(screen.getByText('Your story starts here')).toBeVisible()
  })

  it('opens an unfinished view without inviting personal data entry', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: 'Assets' }))
    expect(
      screen.getByRole('heading', { level: 1, name: 'Assets' }),
    ).toBeVisible()
    expect(screen.getByText('Assets is not available yet.')).toBeVisible()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Assets' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    await user.click(screen.getByRole('button', { name: 'Back to overview' }))
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'A little less to remember.',
    )
  })
})
