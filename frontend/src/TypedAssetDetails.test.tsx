import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { TypedAssetDetails } from './TypedAssetDetails'

afterEach(() => vi.unstubAllGlobals())
it('preserves displayed unknown fields and corrects a selected sourced statement', async () => {
  const fieldId = 'b'.repeat(32)
  const type = {
    id: 'type',
    name: 'Vehicle',
    description: '',
    revision: 'r',
    retired: false,
    seed_key: 'vehicle',
    fields: [
      {
        id: fieldId,
        name: 'Winter tire size',
        retired: false,
        system_field: null,
      },
    ],
  }
  const assignment = {
    id: 'assignment',
    predicate: 'profile_asset_type',
    value: 'type',
    subject_id: 'asset',
  }
  const fact = {
    id: 'fact',
    predicate: `profile_template_${fieldId}`,
    label: 'Winter tire size',
    value: '205/55 R16',
    status: 'stated',
    subject_id: 'asset',
    superseded_at: null,
    recorded_at: 1,
    evidence: [{ source_id: 'source', quote: '205/55 R16' }],
  }
  let posted: Record<string, unknown> | null = null
  const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      posted = JSON.parse(String(init.body))
      return new Response('{}')
    }
    if (path.includes('/assets/'))
      return new Response(
        JSON.stringify({
          assignments: [assignment],
          facts: [fact],
          next_cursor: null,
        }),
      )
    return new Response(JSON.stringify({ items: [type] }))
  })
  vi.stubGlobal('fetch', fetcher)
  const source = vi.fn(async () => {})
  render(
    <TypedAssetDetails
      assetId="asset"
      csrfToken="csrf"
      onEvidence={source}
      onChanged={vi.fn(async () => {})}
    />,
  )
  const user = userEvent.setup()
  await user.click(
    screen.getByRole('button', { name: 'Asset type & custom fields' }),
  )
  await user.click(
    await screen.findByRole('button', { name: 'Correct Winter tire size' }),
  )
  await user.clear(screen.getByLabelText('Field value'))
  await user.type(screen.getByLabelText('Field value'), '215/55 R16')
  await user.type(
    screen.getByLabelText('Evidence or your statement'),
    'My corrected size is 215/55 R16.',
  )
  await user.click(screen.getByRole('button', { name: 'Save field statement' }))
  await waitFor(() =>
    expect(posted).toMatchObject({
      type_id: 'type',
      field_id: fieldId,
      replaces_id: 'fact',
      value: '215/55 R16',
    }),
  )
  await user.click(screen.getByRole('button', { name: 'View field evidence' }))
  expect(source).toHaveBeenCalledWith('source')
})
