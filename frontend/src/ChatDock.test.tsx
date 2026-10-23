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

function dockButton(panel: string, edge: string) {
  return screen.getByRole('button', { name: `Dock ${panel} ${edge}` })
}

function dockedEdge(panel: string) {
  const group = screen.getByRole('group', {
    name: `${panel[0].toUpperCase() + panel.slice(1)} dock position`,
  })
  return within(group)
    .getAllByRole('button')
    .find((button) => button.getAttribute('aria-pressed') === 'true')
    ?.getAttribute('aria-label')
    ?.split(' ')
    .at(-1)
}

it('keeps the assistant and its draft through docking and collapse, with private layout preferences', async () => {
  const user = userEvent.setup()
  const { unmount } = render(
    <ChatDock userId="one" page={<main>Page</main>}>
      <Draft />
    </ChatDock>,
  )
  await user.type(screen.getByLabelText('Synthetic draft'), 'Unsaved message')
  await user.click(dockButton('assistant', 'left'))
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
  expect(dockedEdge('assistant')).toBe('right')
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
  await user.click(dockButton('assistant', 'top'))
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
  await user.click(dockButton('assistant', 'right'))
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
    await user.click(dockButton('assistant', String(edge)))
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
  expect(dockedEdge('assistant')).toBe('bottom')
  expect(screen.getByRole('separator')).toHaveAttribute('aria-valuenow', '50')
})

it('resizes side docks vertically when the narrow-screen fallback is active', () => {
  vi.stubGlobal('innerWidth', 600)
  const { container } = render(dock())
  expect(container.firstElementChild).toHaveClass('dock-bottom')
  // Edge choices only apply to wide screens, so narrow screens hide them.
  expect(
    screen.queryByRole('group', { name: 'Assistant dock position' }),
  ).not.toBeInTheDocument()
  const handle = screen.getByRole('separator')
  expect(handle).toHaveAttribute('aria-orientation', 'horizontal')
  fireEvent.keyDown(handle, { key: 'ArrowUp' })
  expect(handle).toHaveAttribute('aria-valuenow', '52')
  vi.stubGlobal('innerWidth', 1200)
  fireEvent(window, new Event('resize'))
  expect(handle).toHaveAttribute('aria-orientation', 'vertical')
  expect(handle).toHaveAttribute('aria-valuenow', '38')
  expect(dockedEdge('assistant')).toBe('right')
})

it('keeps the assistant below the page on a portrait tablet', () => {
  vi.stubGlobal('innerWidth', 820)
  const { container } = render(dock())
  expect(container.firstElementChild).toHaveClass('dock-bottom')
  expect(container.firstElementChild).not.toHaveClass('dock-collapsed')
})

it('starts collapsed on a phone until the person opens it', async () => {
  vi.stubGlobal('innerWidth', 390)
  const { container } = render(dock())
  expect(container.firstElementChild).toHaveClass(
    'dock-bottom',
    'dock-collapsed',
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Expand assistant' }),
  )
  expect(screen.getByLabelText('Synthetic draft')).toBeVisible()
  expect(
    JSON.parse(localStorage.getItem('lifegather-chat-dock:one')!),
  ).toMatchObject({ collapsed: false })
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

it('drags the assistant header to an edge and collapses to a rail on that edge', async () => {
  vi.stubGlobal('PointerEvent', MouseEvent)
  const user = userEvent.setup()
  const { container } = render(dock())
  await user.type(screen.getByLabelText('Synthetic draft'), 'Keep this')
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
  const header = screen.getByText('LifeGather assistant')
  fireEvent.pointerDown(header, { button: 0, clientX: 800, clientY: 20 })
  fireEvent.pointerMove(header, { clientX: 40, clientY: 500 })
  expect(container.querySelector('.dock-drop-zone[data-active]')).toHaveClass(
    'dock-drop-left',
  )
  fireEvent.pointerUp(header)
  expect(dockedEdge('assistant')).toBe('left')
  expect(container.firstElementChild).toHaveClass('dock-left')
  await user.click(screen.getByRole('button', { name: 'Collapse assistant' }))
  expect(container.firstElementChild).toHaveClass('dock-left', 'dock-collapsed')
  expect(screen.getByLabelText('Synthetic draft')).not.toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Expand assistant' }))
  expect(screen.getByLabelText('Synthetic draft')).toHaveValue('Keep this')
  expect(
    JSON.parse(localStorage.getItem('lifegather-chat-dock:one')!),
  ).toMatchObject({ edge: 'left', collapsed: false })
})

it('does not start a drag from the header on narrow screens', () => {
  vi.stubGlobal('PointerEvent', MouseEvent)
  vi.stubGlobal('innerWidth', 600)
  const { container } = render(dock())
  const header = screen.getByText('LifeGather assistant')
  fireEvent.pointerDown(header, { button: 0, clientX: 300, clientY: 900 })
  fireEvent.pointerMove(header, { clientX: 20, clientY: 400 })
  expect(container.querySelector('.dock-drop-zones')).not.toBeInTheDocument()
  expect(container.firstElementChild).toHaveClass('dock-bottom')
})
