import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { AssetTypeManager } from './AssetTypeManager'
import { ManualAssetForm } from './ManualAssetForm'

afterEach(() => vi.unstubAllGlobals())
const vehicle = {
  id: 'vehicle',
  name: 'Vehicle',
  description: '',
  retired: false,
  revision: 'r1',
  seed_key: 'vehicle',
  fields: [
    {
      id: 'a'.repeat(32),
      name: 'Tire size',
      system_field: null,
      retired: false,
    },
  ],
}

it('edits defaults, adds a field and retries the exact definition after uncertain save', async () => {
  const bodies: string[] = []
  let writes = 0
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_path: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        bodies.push(String(init.body))
        writes++
        if (writes === 1) throw new Error('network')
        return new Response(JSON.stringify({ ...vehicle, revision: 'r2' }))
      }
      return new Response(JSON.stringify({ items: [vehicle] }))
    }),
  )
  render(<AssetTypeManager csrfToken="csrf" />)
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Edit Vehicle' }))
  await user.click(screen.getByRole('button', { name: 'Add field' }))
  await user.type(screen.getByLabelText('Field 2 name'), 'Winter tire size')
  await user.click(screen.getByRole('button', { name: 'Save type' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('uncertain')
  expect(screen.getByLabelText('Type name')).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Retry same change' }))
  await waitFor(() => expect(bodies).toHaveLength(2))
  expect(bodies[1]).toBe(bodies[0])
  expect(JSON.parse(bodies[0])).toMatchObject({
    type_id: 'vehicle',
    expected_revision: 'r1',
    fields: [{ id: 'a'.repeat(32) }, { name: 'Winter tire size', id: null }],
  })
})

it('uses the selected type in manual duplicate checks and the atomic save', async () => {
  const fetcher = vi.fn(async (path: string) => {
    if (path === '/api/asset-types')
      return new Response(JSON.stringify({ items: [vehicle] }))
    if (path.endsWith('/preview'))
      return new Response(JSON.stringify({ candidates: [], reliable_ids: [] }))
    return new Response(
      JSON.stringify({
        asset: { id: 'asset', name: 'Test car' },
        created: true,
        source_id: 's',
      }),
    )
  })
  vi.stubGlobal('fetch', fetcher)
  const saved = vi.fn(async () => {})
  render(
    <ManualAssetForm
      csrfToken="csrf"
      onSaved={saved}
      onOpen={vi.fn()}
      onCancel={vi.fn()}
    />,
  )
  const user = userEvent.setup()
  expect(screen.getByLabelText('Asset name')).toHaveFocus()
  await screen.findByRole('option', { name: 'Vehicle' })
  const select = screen.getByLabelText('Asset type')
  await user.selectOptions(select, 'vehicle')
  // The same dropdown stays in place; the type only adds a details group.
  expect(screen.getAllByRole('combobox')).toEqual([select])
  expect(
    screen.getByRole('group', { name: 'Vehicle details' }),
  ).toBeInTheDocument()
  await user.type(screen.getByLabelText('Tire size'), '205/55 R16')
  await user.type(screen.getByLabelText('Asset name'), 'Test car')
  await user.click(screen.getByLabelText('I currently own this item'))
  await user.click(screen.getByRole('button', { name: 'Save asset' }))
  await waitFor(() => expect(saved).toHaveBeenCalled())
  const call = fetcher.mock.calls.find(([path]) => path.endsWith('/preview'))!
  expect(
    JSON.parse((call as unknown as [string, RequestInit])[1].body as string),
  ).toMatchObject({
    type_id: 'vehicle',
    type_revision: 'r1',
    type_values: [{ field_id: 'a'.repeat(32), value: '205/55 R16' }],
  })
})
