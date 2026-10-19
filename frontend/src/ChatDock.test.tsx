import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { useState } from 'react'
import { ChatDock } from './ChatDock'

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

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
  expect(screen.getByLabelText('Assistant dock position')).toHaveValue('right')
})

function dock() {
  return (
    <ChatDock userId="one" page={<main>Page</main>}>
      <Draft />
    </ChatDock>
  )
}

it('resizes by keyboard, bounds sizes and remembers separate width/height per account', async () => {
  const user = userEvent.setup()
  const view = render(dock())
  let handle = screen.getByRole('separator', { name: 'Resize assistant' })
  expect(handle).toHaveAttribute('aria-orientation', 'vertical')
  fireEvent.keyDown(handle, { key: 'ArrowLeft' })
  expect(handle).toHaveAttribute('aria-valuenow', '40')
  fireEvent.keyDown(handle, { key: 'End' })
  fireEvent.keyDown(handle, { key: 'ArrowLeft' })
  expect(handle).toHaveAttribute('aria-valuenow', '75')
  await user.selectOptions(
    screen.getByLabelText('Assistant dock position'),
    'top',
  )
  handle = screen.getByRole('separator')
  expect(handle).toHaveAttribute('aria-orientation', 'horizontal')
  fireEvent.keyDown(handle, { key: 'ArrowDown' })
  expect(handle).toHaveAttribute('aria-valuenow', '52')
  fireEvent.keyDown(handle, { key: 'Home' })
  fireEvent.keyDown(handle, { key: 'ArrowUp' })
  expect(handle).toHaveAttribute('aria-valuenow', '25')
  view.unmount()
  const second = render(dock())
  expect(screen.getByRole('separator')).toHaveAttribute('aria-valuenow', '25')
  await user.selectOptions(
    screen.getByLabelText('Assistant dock position'),
    'right',
  )
  expect(screen.getByRole('separator')).toHaveAttribute('aria-valuenow', '75')
  await user.click(screen.getByRole('button', { name: 'Collapse assistant' }))
  expect(screen.queryByRole('separator')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Expand assistant' }))
  expect(screen.getByRole('separator')).toHaveAttribute('aria-valuenow', '75')
  second.unmount()
  render(
    <ChatDock userId="two" page={<main>Page</main>}>
      <Draft />
    </ChatDock>,
  )
  expect(screen.getByRole('separator')).toHaveAttribute('aria-valuenow', '38')
})

it.each([
  ['right', 600, 300, 40],
  ['left', 600, 300, 60],
  ['top', 600, 300, 30],
  ['bottom', 600, 300, 70],
])(
  'resizes the %s dock by pointer without losing drafts',
  async (edge, x, y, size) => {
    vi.stubGlobal('PointerEvent', MouseEvent)
    const user = userEvent.setup()
    const { container } = render(dock())
    await user.type(screen.getByLabelText('Synthetic draft'), 'Keep this')
    await user.selectOptions(
      screen.getByLabelText('Assistant dock position'),
      String(edge),
    )
    vi.spyOn(
      container.firstElementChild!,
      'getBoundingClientRect',
    ).mockReturnValue({
      left: 0,
      right: 1000,
      top: 0,
      bottom: 1000,
      width: 1000,
      height: 1000,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })
    const handle = screen.getByRole('separator')
    fireEvent.pointerDown(handle, { button: 0, clientX: 500, clientY: 500 })
    fireEvent.pointerMove(handle, { clientX: x, clientY: y })
    fireEvent.pointerUp(handle)
    expect(handle).toHaveAttribute('aria-valuenow', String(size))
    fireEvent.pointerMove(handle, { clientX: 900, clientY: 900 })
    expect(handle).toHaveAttribute('aria-valuenow', String(size))
    expect(screen.getByLabelText('Synthetic draft')).toHaveValue('Keep this')
  },
)

it('preserves legacy positions and sanitizes invalid saved dimensions', () => {
  localStorage.setItem(
    'lifegather-chat-dock:one',
    JSON.stringify({
      edge: 'bottom',
      collapsed: false,
      width: 'bad',
      height: 900,
    }),
  )
  render(dock())
  expect(screen.getByLabelText('Assistant dock position')).toHaveValue('bottom')
  expect(screen.getByRole('separator')).toHaveAttribute('aria-valuenow', '50')
})

it('resizes side docks vertically when the narrow-screen fallback is active', () => {
  vi.stubGlobal('innerWidth', 600)
  render(dock())
  expect(screen.getByLabelText('Assistant dock position')).toHaveValue('right')
  const handle = screen.getByRole('separator')
  expect(handle).toHaveAttribute('aria-orientation', 'horizontal')
  fireEvent.keyDown(handle, { key: 'ArrowUp' })
  expect(handle).toHaveAttribute('aria-valuenow', '52')
  vi.stubGlobal('innerWidth', 1200)
  fireEvent(window, new Event('resize'))
  expect(handle).toHaveAttribute('aria-orientation', 'vertical')
  expect(handle).toHaveAttribute('aria-valuenow', '38')
})

it('keeps resizing usable if browser preference storage is unavailable', () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new Error('Unavailable')
  })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new Error('Unavailable')
  })
  render(dock())
  fireEvent.keyDown(screen.getByRole('separator'), { key: 'ArrowLeft' })
  expect(screen.getByRole('separator')).toHaveAttribute('aria-valuenow', '40')
})
