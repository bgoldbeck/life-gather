import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Workspace as App } from './App'

afterEach(() => vi.unstubAllGlobals())

describe('LifeGather shell', () => {
  it('shows the planned navigation and an honest empty overview', () => {
    render(<App />)
    const navigation = screen.getByRole('navigation', {
      name: 'Main navigation',
    })
    for (const name of [
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
    expect(
      within(navigation).queryByRole('button', { name: 'Chat' }),
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('region', { name: 'LifeGather assistant' }),
    ).toBeVisible()
  })

  it('opens the available memory library and returns to overview', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ items: [], next_cursor: null })),
      ),
    )
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: 'Memories' }))
    expect(
      screen.getByRole('heading', { level: 1, name: 'Memories' }),
    ).toBeVisible()
    expect(
      await screen.findByText(
        'No saved evidence matches this view. Save a note or review text from a photo or PDF.',
      ),
    ).toBeVisible()
    expect(screen.getByLabelText('Search saved evidence')).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Memories' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    await user.click(screen.getByRole('button', { name: 'Overview' }))
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'A little less to remember.',
    )
  })
})
