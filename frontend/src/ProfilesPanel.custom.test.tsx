import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ProfilesPanel } from './ProfilesPanel'

afterEach(() => vi.unstubAllGlobals())

type Detail = {
  field: string
  custom_name: string
  value: string | null
  status: string
  text: string
  replaces_id: string | null
  operation_key: string
  valid_from: string | null
  valid_to: string | null
}
const entity = {
  id: 'car',
  name: 'Synthetic car',
  kind: 'asset',
  source_id: 'source',
}
function fact(
  id: string,
  value: string | null,
  predicate = 'profile_custom_fuel_type',
) {
  return {
    id,
    predicate,
    value,
    status: value === null ? 'unknown' : 'stated',
    recorded_at: 100,
    superseded_at: null as number | null,
    valid_from: null as string | null,
    valid_to: null as string | null,
    object_id: null,
    evidence: [{ source_id: 'source' }],
  }
}
async function setup({
  correction = false,
  failFirst = false,
  predicate = 'profile_custom_tire_size',
} = {}) {
  const posts: Detail[] = []
  let rows = correction ? [fact('old', 'Regular')] : []
  const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.startsWith('/api/graph/entities'))
      return Response.json({ items: [entity], next_cursor: null })
    if (path.startsWith('/api/history/fields'))
      return Response.json({
        items: rows.map((row) => ({
          ...row,
          previous: null,
          origin: null,
          proposal_origin: null,
          evidence: [],
          more_evidence: false,
        })),
        next_cursor: null,
      })
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body)) as Detail
      posts.push(body)
      if (failFirst && posts.length === 1)
        return new Response('unavailable', { status: 503 })
      rows = rows.map((row) =>
        row.id === body.replaces_id ? { ...row, superseded_at: 101 } : row,
      )
      rows.push({
        ...fact('saved', body.value, predicate),
        status: body.status,
        valid_from: body.valid_from,
        valid_to: body.valid_to,
      })
      return Response.json(rows.at(-1))
    }
    return Response.json({
      entity,
      facts: path.includes('history=true')
        ? rows
        : rows.filter((row) => row.superseded_at === null),
      next_cursor: null,
    })
  })
  vi.stubGlobal('fetch', fetcher)
  render(<ProfilesPanel csrfToken="csrf" />)
  await screen.findByRole('heading', { name: 'Synthetic car' })
  return { posts, fetcher, user: userEvent.setup() }
}

it('creates a named sourced detail and displays its readable correction action', async () => {
  const { posts, user } = await setup()
  await user.selectOptions(screen.getByLabelText('Detail type'), 'custom')
  await user.type(screen.getByLabelText('Detail name'), 'Tire size')
  await user.type(screen.getByLabelText('Exact value'), '205/55R16')
  await user.type(
    screen.getByLabelText('Original evidence or your statement'),
    'Synthetic tire label 205/55R16.',
  )
  await user.click(screen.getByRole('button', { name: 'Save sourced detail' }))
  expect(
    await screen.findByRole('button', { name: 'Correct tire size' }),
  ).toBeVisible()
  expect(posts[0]).toMatchObject({
    field: 'custom',
    custom_name: 'Tire size',
    value: '205/55R16',
    text: 'Synthetic tire label 205/55R16.',
    status: 'stated',
    replaces_id: null,
  })
  expect(screen.queryByText('profile_custom_tire_size')).not.toBeInTheDocument()
})

it('records an explicitly unknown custom detail with valid-world dates', async () => {
  const { posts, user } = await setup({ predicate: 'profile_custom_fuel_type' })
  await user.selectOptions(screen.getByLabelText('Detail type'), 'custom')
  await user.type(screen.getByLabelText('Detail name'), 'Fuel type')
  await user.selectOptions(screen.getByLabelText('Confidence'), 'unknown')
  expect(screen.getByLabelText('Exact value')).toBeDisabled()
  await user.type(
    screen.getByLabelText('Original evidence or your statement'),
    'Synthetic fuel type is unknown.',
  )
  await user.type(screen.getByLabelText('Valid from (optional)'), '2026-10-19')
  await user.click(screen.getByRole('button', { name: 'Save sourced detail' }))
  expect(
    await screen.findByRole('button', { name: 'Correct fuel type' }),
  ).toBeVisible()
  expect(posts[0]).toMatchObject({
    field: 'custom',
    custom_name: 'Fuel type',
    value: null,
    status: 'unknown',
    valid_from: '2026-10-19',
  })
})

it.each(['VIN', 'Tire/size'])(
  'rejects an invalid or reserved custom name before submitting: %s',
  async (name) => {
    const { posts, user } = await setup()
    await user.selectOptions(screen.getByLabelText('Detail type'), 'custom')
    await user.type(screen.getByLabelText('Detail name'), name)
    await user.type(screen.getByLabelText('Exact value'), 'Synthetic')
    await user.type(
      screen.getByLabelText('Original evidence or your statement'),
      'Synthetic statement.',
    )
    await user.click(
      screen.getByRole('button', { name: 'Save sourced detail' }),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'choose its existing type',
    )
    expect(posts).toHaveLength(0)
  },
)

it('locks the custom name during correction and safely retries the same request', async () => {
  const { posts, fetcher, user } = await setup({
    correction: true,
    failFirst: true,
    predicate: 'profile_custom_fuel_type',
  })
  await user.click(screen.getByRole('button', { name: 'Correct fuel type' }))
  expect(screen.getByLabelText('Detail type')).toBeDisabled()
  expect(screen.getByLabelText('Detail name')).toBeDisabled()
  expect(screen.getByLabelText('Detail name')).toHaveValue('fuel type')
  await user.clear(screen.getByLabelText('Exact value'))
  await user.type(screen.getByLabelText('Exact value'), 'Premium')
  await user.type(
    screen.getByLabelText('Original evidence or your statement'),
    'Synthetic correction: Premium.',
  )
  await user.click(screen.getByRole('button', { name: 'Save sourced detail' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Unable to save')
  expect(screen.getByLabelText('Exact value')).toHaveValue('Premium')
  await user.click(screen.getByRole('button', { name: 'Save sourced detail' }))
  await screen.findByText('Detail saved with original evidence.')
  expect(posts).toHaveLength(2)
  expect(posts[0]).toEqual(posts[1])
  expect(posts[1]).toMatchObject({
    field: 'custom',
    custom_name: 'fuel type',
    replaces_id: 'old',
    value: 'Premium',
  })
  await user.click(
    screen.getByRole('button', { name: 'View fuel type history' }),
  )
  expect(screen.getByLabelText('fuel type change history')).toBeVisible()
  expect(
    fetcher.mock.calls.some(([path]) =>
      path.includes('field=profile_custom_fuel_type'),
    ),
  ).toBe(true)
  await user.click(screen.getByLabelText('Include correction history'))
  expect(await screen.findByText('— superseded')).toBeVisible()
})
