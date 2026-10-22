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

it('defaults navigation left and moves every edge without losing the page or assistant draft', async () => {
  const user = userEvent.setup()
  render(<Workspace userId="one" />)
  const position = screen.getByRole('combobox', {
    name: 'Navigation dock position',
  })
  expect(position).toHaveValue('left')
  expect(
    screen.getByRole('combobox', { name: 'Assistant dock position' }),
  ).toHaveValue('right')
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
    await user.selectOptions(position, edge)
    expect(screen.getByRole('heading', { name: 'Memories' })).toBeVisible()
    expect(screen.getByLabelText('Message your assistant')).toHaveValue(
      'Keep this draft',
    )
    expect(
      screen.getByRole('combobox', { name: 'Assistant dock position' }),
    ).toHaveValue('right')
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
  await user.selectOptions(
    screen.getByRole('combobox', { name: 'Navigation dock position' }),
    'bottom',
  )
  handle = screen.getByRole('separator', { name: 'Resize navigation' })
  expect(handle).toHaveAttribute('aria-orientation', 'horizontal')
  fireEvent.keyDown(handle, { key: 'ArrowUp' })
  expect(handle).toHaveAttribute('aria-valuenow', '170')
  fireEvent.keyDown(handle, { key: 'End' })
  expect(handle).toHaveAttribute('aria-valuenow', '320')
  first.unmount()
  const second = render(<Workspace userId="one" />)
  expect(
    screen.getByRole('combobox', { name: 'Navigation dock position' }),
  ).toHaveValue('bottom')
  expect(
    screen.getByRole('separator', { name: 'Resize navigation' }),
  ).toHaveAttribute('aria-valuenow', '320')
  await user.selectOptions(
    screen.getByRole('combobox', { name: 'Navigation dock position' }),
    'left',
  )
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
  expect(
    screen.getByRole('combobox', { name: 'Navigation dock position' }),
  ).toHaveValue('left')
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
    await user.selectOptions(
      screen.getByRole('combobox', { name: 'Navigation dock position' }),
      String(edge),
    )
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
  expect(
    screen.getByRole('combobox', { name: 'Navigation dock position' }),
  ).toHaveValue('bottom')
  expect(localStorage.getItem('lifegather-navigation-dock:one')).toBe(original)
  vi.stubGlobal('innerWidth', 1200)
  fireEvent(window, new Event('resize'))
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
  expect(
    screen.getByRole('combobox', { name: 'Navigation dock position' }),
  ).toHaveValue('left')
  first.unmount()
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new Error('Unavailable')
  })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new Error('Unavailable')
  })
  render(<Workspace userId="one" />)
  await userEvent.selectOptions(
    screen.getByRole('combobox', { name: 'Navigation dock position' }),
    'top',
  )
  fireEvent.keyDown(
    screen.getByRole('separator', { name: 'Resize navigation' }),
    { key: 'Home' },
  )
  expect(
    screen.getByRole('separator', { name: 'Resize navigation' }),
  ).toHaveAttribute('aria-valuenow', '112')
})
