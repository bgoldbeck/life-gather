import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Workspace } from './App'

beforeEach(() => {
  vi.stubGlobal('innerWidth', 1200)
  vi.stubGlobal('innerHeight', 1000)
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(JSON.stringify({ items: [], next_cursor: null })),
    ),
  )
})
afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

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

it('defaults navigation left and moves every edge without losing the page or assistant draft', async () => {
  const user = userEvent.setup()
  render(<Workspace userId="one" />)
  expect(dockedEdge('navigation')).toBe('left')
  expect(dockedEdge('assistant')).toBe('right')
  await user.type(
    screen.getByLabelText('Message your assistant'),
    'Keep this draft',
  )
  await user.click(
    within(
      screen.getByRole('navigation', { name: 'Main navigation' }),
    ).getByRole('button', { name: 'Memories' }),
  )
  for (const edge of ['top', 'bottom', 'right', 'left']) {
    await user.click(dockButton('navigation', edge))
    expect(screen.getByRole('heading', { name: 'Memories' })).toBeVisible()
    expect(screen.getByLabelText('Message your assistant')).toHaveValue(
      'Keep this draft',
    )
    expect(dockedEdge('assistant')).toBe('right')
  }
  expect(localStorage.getItem('lifegather-navigation-dock:one')).not.toContain(
    'Keep this draft',
  )
})

it('resizes by keyboard with independent dimensions, persists per account and resets only navigation', async () => {
  const user = userEvent.setup()
  const assistant = JSON.stringify({
    edge: 'left',
    width: 40,
    height: 50,
    collapsed: false,
  })
  localStorage.setItem('lifegather-chat-dock:one', assistant)
  const first = render(<Workspace userId="one" />)
  let handle = screen.getByRole('separator', { name: 'Resize navigation' })
  expect(handle).toHaveAttribute('aria-orientation', 'vertical')
  fireEvent.keyDown(handle, { key: 'ArrowRight' })
  expect(handle).toHaveAttribute('aria-valuenow', '226')
  await user.click(dockButton('navigation', 'bottom'))
  handle = screen.getByRole('separator', { name: 'Resize navigation' })
  expect(handle).toHaveAttribute('aria-orientation', 'horizontal')
  fireEvent.keyDown(handle, { key: 'ArrowUp' })
  expect(handle).toHaveAttribute('aria-valuenow', '170')
  fireEvent.keyDown(handle, { key: 'End' })
  expect(handle).toHaveAttribute('aria-valuenow', '320')
  first.unmount()
  const second = render(<Workspace userId="one" />)
  expect(dockedEdge('navigation')).toBe('bottom')
  expect(
    screen.getByRole('separator', { name: 'Resize navigation' }),
  ).toHaveAttribute('aria-valuenow', '320')
  await user.click(dockButton('navigation', 'left'))
  expect(
    screen.getByRole('separator', { name: 'Resize navigation' }),
  ).toHaveAttribute('aria-valuenow', '226')
  await user.click(
    screen.getByRole('button', { name: 'Reset navigation layout' }),
  )
  expect(
    screen.getByRole('separator', { name: 'Resize navigation' }),
  ).toHaveAttribute('aria-valuenow', '216')
  expect(localStorage.getItem('lifegather-chat-dock:one')).toBe(assistant)
  second.unmount()
  render(<Workspace userId="two" />)
  expect(dockedEdge('navigation')).toBe('left')
  expect(
    screen.getByRole('separator', { name: 'Resize navigation' }),
  ).toHaveAttribute('aria-valuenow', '216')
})

it.each([
  ['left', 280, 300, 280],
  ['right', 720, 300, 280],
  ['top', 300, 180, 180],
  ['bottom', 300, 620, 180],
])(
  'resizes the %s navigation by pointer and stops after cancellation',
  async (edge, x, y, expected) => {
    vi.stubGlobal('PointerEvent', MouseEvent)
    const user = userEvent.setup()
    const { container } = render(<Workspace userId="one" />)
    await user.click(dockButton('navigation', String(edge)))
    vi.spyOn(
      container.querySelector('.app-layout')!,
      'getBoundingClientRect',
    ).mockReturnValue({
      left: 0,
      right: 1000,
      top: 0,
      bottom: 800,
      width: 1000,
      height: 800,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })
    const handle = screen.getByRole('separator', { name: 'Resize navigation' })
    fireEvent.pointerDown(handle, { button: 0, clientX: 500, clientY: 400 })
    fireEvent.pointerMove(handle, { clientX: x, clientY: y })
    expect(handle).toHaveAttribute('aria-valuenow', String(expected))
    fireEvent.pointerCancel(handle)
    fireEvent.pointerMove(handle, { clientX: 900, clientY: 700 })
    expect(handle).toHaveAttribute('aria-valuenow', String(expected))
  },
)

it('uses compact navigation on narrow screens without overwriting desktop position or size', () => {
  const original = JSON.stringify({ edge: 'bottom', width: 300, height: 200 })
  localStorage.setItem('lifegather-navigation-dock:one', original)
  const { container } = render(<Workspace userId="one" />)
  vi.stubGlobal('innerWidth', 390)
  fireEvent(window, new Event('resize'))
  expect(container.querySelector('.app-layout')).toHaveClass(
    'navigation-compact',
  )
  expect(
    screen.queryByRole('separator', { name: 'Resize navigation' }),
  ).not.toBeInTheDocument()
  // Edge and reset choices only apply to wide screens.
  expect(
    screen.queryByRole('group', { name: 'Navigation dock position' }),
  ).not.toBeInTheDocument()
  expect(
    screen.queryByRole('button', { name: 'Reset navigation layout' }),
  ).not.toBeInTheDocument()
  expect(localStorage.getItem('lifegather-navigation-dock:one')).toBe(original)
  vi.stubGlobal('innerWidth', 1200)
  fireEvent(window, new Event('resize'))
  expect(dockedEdge('navigation')).toBe('bottom')
  expect(
    screen.getByRole('separator', { name: 'Resize navigation' }),
  ).toHaveAttribute('aria-valuenow', '200')
})

it('clamps a saved width to a smaller viewport without rewriting the saved dimension', () => {
  const original = JSON.stringify({ edge: 'right', width: 400, height: 160 })
  localStorage.setItem('lifegather-navigation-dock:one', original)
  render(<Workspace userId="one" />)
  vi.stubGlobal('innerWidth', 900)
  fireEvent(window, new Event('resize'))
  expect(
    screen.getByRole('separator', { name: 'Resize navigation' }),
  ).toHaveAttribute('aria-valuenow', '288')
  expect(localStorage.getItem('lifegather-navigation-dock:one')).toBe(original)
})

it('rejects invalid stored layout and remains usable without browser storage', async () => {
  localStorage.setItem(
    'lifegather-navigation-dock:one',
    JSON.stringify({ edge: 'unsafe', width: 900, height: 'bad' }),
  )
  const first = render(<Workspace userId="one" />)
  expect(dockedEdge('navigation')).toBe('left')
  first.unmount()
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new Error('Unavailable')
  })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new Error('Unavailable')
  })
  render(<Workspace userId="one" />)
  await userEvent.click(dockButton('navigation', 'top'))
  fireEvent.keyDown(
    screen.getByRole('separator', { name: 'Resize navigation' }),
    { key: 'Home' },
  )
  expect(
    screen.getByRole('separator', { name: 'Resize navigation' }),
  ).toHaveAttribute('aria-valuenow', '112')
})

function mockArea(element: Element) {
  vi.spyOn(element, 'getBoundingClientRect').mockReturnValue({
    left: 0,
    right: 1000,
    top: 0,
    bottom: 800,
    width: 1000,
    height: 800,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  })
}

it('drags navigation by its header onto a highlighted drop zone and snaps there', async () => {
  vi.stubGlobal('PointerEvent', MouseEvent)
  const user = userEvent.setup()
  const { container } = render(<Workspace userId="one" />)
  await user.type(screen.getByLabelText('Message your assistant'), 'Draft')
  mockArea(container.querySelector('.app-layout')!)
  const header = container.querySelector('.brand')!
  fireEvent.pointerDown(header, { button: 0, clientX: 60, clientY: 30 })
  fireEvent.pointerMove(header, { clientX: 62, clientY: 31 })
  expect(container.querySelector('.dock-drop-zones')).not.toBeInTheDocument()
  fireEvent.pointerMove(header, { clientX: 960, clientY: 400 })
  expect(container.querySelector('.dock-drop-zone[data-active]')).toHaveClass(
    'dock-drop-right',
  )
  expect(screen.getByRole('status')).toHaveTextContent(
    'Release to dock navigation right',
  )
  fireEvent.pointerUp(header)
  expect(container.querySelector('.dock-drop-zones')).not.toBeInTheDocument()
  expect(container.querySelector('.app-layout')).toHaveClass('navigation-right')
  expect(dockedEdge('navigation')).toBe('right')
  expect(
    JSON.parse(localStorage.getItem('lifegather-navigation-dock:one')!),
  ).toMatchObject({ edge: 'right' })
  expect(screen.getByLabelText('Message your assistant')).toHaveValue('Draft')
})

it('cancels a navigation drag with Escape and ignores presses on nav buttons', () => {
  vi.stubGlobal('PointerEvent', MouseEvent)
  const { container } = render(<Workspace userId="one" />)
  mockArea(container.querySelector('.app-layout')!)
  const header = container.querySelector('.brand')!
  fireEvent.pointerDown(header, { button: 0, clientX: 60, clientY: 30 })
  fireEvent.pointerMove(header, { clientX: 500, clientY: 20 })
  expect(container.querySelector('.dock-drop-zone[data-active]')).toHaveClass(
    'dock-drop-top',
  )
  fireEvent.keyDown(window, { key: 'Escape' })
  expect(container.querySelector('.dock-drop-zones')).not.toBeInTheDocument()
  fireEvent.pointerUp(header)
  expect(dockedEdge('navigation')).toBe('left')
  const memories = within(
    screen.getByRole('navigation', { name: 'Main navigation' }),
  ).getByRole('button', { name: 'Memories' })
  fireEvent.pointerDown(memories, { button: 0, clientX: 60, clientY: 200 })
  fireEvent.pointerMove(memories, { clientX: 960, clientY: 400 })
  expect(container.querySelector('.dock-drop-zones')).not.toBeInTheDocument()
})

it('collapses navigation to a remembered icon rail that keeps every destination', async () => {
  const user = userEvent.setup()
  const first = render(<Workspace userId="one" />)
  await user.click(screen.getByRole('button', { name: 'Collapse navigation' }))
  expect(first.container.querySelector('.app-layout')).toHaveClass(
    'navigation-collapsed',
  )
  expect(
    screen.queryByRole('separator', { name: 'Resize navigation' }),
  ).not.toBeInTheDocument()
  await user.click(
    within(
      screen.getByRole('navigation', { name: 'Main navigation' }),
    ).getByRole('button', { name: 'Memories' }),
  )
  expect(screen.getByRole('heading', { name: 'Memories' })).toBeVisible()
  first.unmount()
  render(<Workspace userId="one" />)
  const expand = screen.getByRole('button', { name: 'Expand navigation' })
  expect(expand).toHaveAttribute('aria-expanded', 'false')
  await user.click(expand)
  expect(
    screen.getByRole('separator', { name: 'Resize navigation' }),
  ).toHaveAttribute('aria-valuenow', '216')
  expect(
    JSON.parse(localStorage.getItem('lifegather-navigation-dock:one')!),
  ).toMatchObject({ edge: 'left', collapsed: false })
})
