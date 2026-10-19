import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it } from 'vitest'
import { useState } from 'react'
import { ChatDock } from './ChatDock'

afterEach(() => localStorage.clear())

function Draft() {
  const [text, setText] = useState('')
  return (
    <input
      aria-label="Synthetic draft"
      value={text}
      onChange={(e) => setText(e.target.value)}
    />
  )
}

it('keeps the assistant and its draft through docking and collapse, with private layout preferences', async () => {
  const user = userEvent.setup()
  const { unmount } = render(
    <ChatDock userId="one" page={<main>Page</main>}>
      <Draft />
    </ChatDock>,
  )
  await user.type(screen.getByLabelText('Synthetic draft'), 'Unsaved message')
  await user.selectOptions(
    screen.getByLabelText('Assistant dock position'),
    'left',
  )
  await user.click(screen.getByRole('button', { name: 'Collapse assistant' }))
  expect(screen.getByLabelText('Synthetic draft')).not.toBeVisible()
  expect(
    within(
      screen.getByRole('region', { name: 'LifeGather assistant' }),
    ).queryByRole('button', { name: /close/i }),
  ).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Expand assistant' }))
  expect(screen.getByLabelText('Synthetic draft')).toHaveValue(
    'Unsaved message',
  )
  expect(localStorage.getItem('lifegather-chat-dock:one')).not.toContain(
    'Unsaved message',
  )
  unmount()
  render(
    <ChatDock userId="two" page={<main>Page</main>}>
      <Draft />
    </ChatDock>,
  )
  expect(screen.getByLabelText('Assistant dock position')).toHaveValue('bottom')
})
