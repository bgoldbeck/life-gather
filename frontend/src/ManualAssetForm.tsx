import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { CandidateComparison } from './CandidateComparison'

type Fields = {
  name: string
  manufacturer: string | null
  model: string | null
  serial: string | null
  notes: string
  ownership_confirmed: boolean
}
type Preview = {
  candidates: { id: string; name: string; can_link: boolean }[]
  reliable_ids: string[]
}
type Submission = Fields & {
  request_id: string
  action: 'new' | 'link'
  asset_id: string | null
  candidate_ids: string[]
}
export type ManualAssetResult = {
  asset: { id: string; name: string }
  source_id: string
  created: boolean
}

export function ManualAssetForm({
  csrfToken,
  refreshSession,
  onSaved,
  onCancel,
  onOpen,
}: {
  csrfToken: string
  refreshSession?: () => Promise<void>
  onSaved: (result: ManualAssetResult) => Promise<void>
  onCancel: () => void
  onOpen: (id: string) => Promise<void>
}) {
  const [fields, setFields] = useState({
    name: '',
    manufacturer: '',
    model: '',
    serial: '',
    notes: '',
  })
  const [owned, setOwned] = useState(false)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [busy, setBusy] = useState(false)
  const [retry, setRetry] = useState(false)
  const [error, setError] = useState('')
  const active = useRef(true)
  const working = useRef(false)
  const pending = useRef<Submission | null>(null)
  const controller = useRef<AbortController | null>(null)
  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
      controller.current?.abort()
    }
  }, [])
  const frozen = busy || retry
  function change(key: keyof typeof fields, value: string) {
    setFields((old) => ({ ...old, [key]: value }))
    setPreview(null)
    setError('')
  }
  function payload(): Fields {
    return {
      ...fields,
      name: fields.name.trim(),
      manufacturer: fields.manufacturer.trim() || null,
      model: fields.model.trim() || null,
      serial: fields.serial.trim() || null,
      ownership_confirmed: owned,
    }
  }
  async function post(path: string, body: object, signal?: AbortSignal) {
    const response = await fetch('/api/assets/manual' + path, {
      method: 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      signal,
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken,
      },
      body: JSON.stringify(body),
    })
    if (response.status === 401) await refreshSession?.()
    return response
  }
  async function save(
    action: 'new' | 'link',
    check: Preview,
    assetId: string | null = null,
  ) {
    const body = pending.current ?? {
      ...payload(),
      action,
      asset_id: assetId,
      candidate_ids: check.candidates.map((row) => row.id),
      request_id: crypto.randomUUID(),
    }
    pending.current = body
    const response = await post('', body)
    if (!response.ok) {
      if ([400, 401, 403, 409, 422].includes(response.status)) {
        pending.current = null
        setRetry(false)
        if (response.status === 409) setPreview(null)
        const failure = (await response.json()) as { detail?: string }
        throw new Error(
          failure.detail ?? 'Unable to save. Check the fields and try again.',
        )
      }
      throw new Error(
        'The save result is uncertain. Retry the same request to avoid duplicates.',
      )
    }
    const result = (await response.json()) as ManualAssetResult
    pending.current = null
    if (active.current) {
      setRetry(false)
      await onSaved(result)
    }
  }
  async function run(operation: () => Promise<void>) {
    if (working.current) return
    working.current = true
    setBusy(true)
    setError('')
    try {
      await operation()
    } catch (caught) {
      if (active.current) {
        setRetry(Boolean(pending.current))
        setError(
          pending.current
            ? 'The save result is uncertain. Retry the same request to avoid duplicates.'
            : (caught as Error).message,
        )
      }
    } finally {
      working.current = false
      if (active.current) setBusy(false)
    }
  }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (pending.current) {
      await run(() =>
        save(
          pending.current!.action,
          preview ?? { candidates: [], reliable_ids: [] },
          pending.current!.asset_id,
        ),
      )
      return
    }
    await run(async () => {
      const abort = new AbortController()
      controller.current = abort
      const response = await post('/preview', payload(), abort.signal)
      if (!response.ok)
        throw new Error(
          'Unable to check duplicates. Check the fields and try again.',
        )
      const check = (await response.json()) as Preview
      if (!active.current) return
      setPreview(check)
      if (!check.candidates.length) await save('new', check)
    })
  }
  return (
    <section className="manual-asset" aria-label="Add asset manually">
      <h2>Add asset</h2>
      <p>
        Record one physical item. Your entry is saved as your statement, with
        its original details and history. Unknown fields can stay blank.
      </p>
      <form onSubmit={(event) => void submit(event)}>
        <fieldset disabled={frozen} className="manual-asset-fields">
          <label>
            Asset name
            <input
              required
              maxLength={200}
              value={fields.name}
              onChange={(event) => change('name', event.target.value)}
            />
          </label>
          <label>
            Manufacturer
            <input
              maxLength={100}
              value={fields.manufacturer}
              required={Boolean(fields.model || fields.serial)}
              onChange={(event) => change('manufacturer', event.target.value)}
            />
          </label>
          <label>
            Model
            <input
              maxLength={100}
              value={fields.model}
              onChange={(event) => change('model', event.target.value)}
            />
          </label>
          <label>
            Serial number
            <input
              maxLength={100}
              value={fields.serial}
              onChange={(event) => change('serial', event.target.value)}
            />
          </label>
          <label className="manual-asset-notes">
            Notes
            <textarea
              maxLength={2000}
              value={fields.notes}
              onChange={(event) => change('notes', event.target.value)}
            />
          </label>
          <label className="manual-asset-notes">
            <input
              required
              type="checkbox"
              checked={owned}
              onChange={(event) => {
                setOwned(event.target.checked)
                setPreview(null)
              }}
            />
            I currently own this item
          </label>
        </fieldset>
        <p>
          A model or serial number needs its manufacturer. No AI provider is
          required.
        </p>
        {error && <p role="alert">{error}</p>}
        {busy && <p role="status">Checking or saving your asset…</p>}
        {preview && preview.candidates.length > 0 && (
          <div aria-label="Possible duplicate assets">
            <h3>Check existing items</h3>
            <p>
              Similar names do not prove two records are the same physical item.
              Inspect a match before linking.
            </p>
            <CandidateComparison
              candidates={preview.candidates}
              onOpen={onOpen}
            />
            {preview.candidates.map((row) => (
              <div key={row.id}>
                <p>
                  {row.name}{' '}
                  {preview.reliable_ids.includes(row.id) &&
                    '· Matching identifier'}
                  {!row.can_link &&
                    ' · Ownership correction: open this item to update ownership first.'}
                </p>
                <Button
                  type="button"
                  variant="outline"
                  disabled={
                    frozen ||
                    !row.can_link ||
                    Boolean(
                      preview.reliable_ids.length &&
                      !preview.reliable_ids.includes(row.id),
                    )
                  }
                  onClick={() => void run(() => save('link', preview, row.id))}
                >
                  Add information to {row.name}
                </Button>
              </div>
            ))}
            {!preview.reliable_ids.length && (
              <Button
                type="button"
                disabled={frozen}
                onClick={() => void run(() => save('new', preview))}
              >
                Create a separate item
              </Button>
            )}
          </div>
        )}
        {(!preview?.candidates.length || retry) && (
          <Button type="submit" disabled={busy}>
            {retry ? 'Retry same save' : 'Save asset'}
          </Button>
        )}
        <Button
          type="button"
          variant="outline"
          disabled={frozen}
          onClick={onCancel}
        >
          Cancel
        </Button>
      </form>
    </section>
  )
}
