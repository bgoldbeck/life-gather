import { useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { FieldHistory } from './FieldHistory'
import {
  typeRequest,
  typeCatalog,
  useTypeWrite,
  type AssetType,
  type TemplateField,
} from './assetTypes'

type Fact = {
  id: string
  predicate: string
  label: string | null
  value: string | null
  status: string
  subject_id: string
  superseded_at: number | null
  recorded_at: number
  valid_from?: string | null
  valid_to?: string | null
  more_evidence?: boolean
  evidence: { source_id: string; quote: string | null }[]
}
type Page = { assignments: Fact[]; facts: Fact[]; next_cursor: string | null }
type Edit = { typeId: string; field: TemplateField; previous: Fact | null }

export function TypedAssetDetails({
  assetId,
  csrfToken,
  refreshSession,
  onEvidence,
  onChanged,
}: {
  assetId: string
  csrfToken: string
  refreshSession?: () => Promise<void>
  onEvidence: (id: string) => Promise<void>
  onChanged: () => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [types, setTypes] = useState<AssetType[]>([])
  const [page, setPage] = useState<Page | null>(null)
  const [selected, setSelected] = useState('')
  const [replace, setReplace] = useState('')
  const [history, setHistory] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [edit, setEdit] = useState<Edit | null>(null)
  const [value, setValue] = useState('')
  const [text, setText] = useState('')
  const [unknown, setUnknown] = useState(false)
  const [validFrom, setValidFrom] = useState('')
  const [validTo, setValidTo] = useState('')
  const [notice, setNotice] = useState('')
  const writer = useTypeWrite(csrfToken, refreshSession)
  const frozen = writer.busy || writer.retry
  const read = useCallback(
    async (signal?: AbortSignal) => {
      const [catalog, record] = await Promise.all([
        typeCatalog(true, signal, refreshSession),
        typeRequest(
          `/assets/${encodeURIComponent(assetId)}?history=${history}`,
          '',
          undefined,
          signal,
          refreshSession,
        ),
      ])
      return { catalog, record }
    },
    [assetId, history, refreshSession],
  )
  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    void read(controller.signal)
      .then(({ catalog, record }) => {
        if (!controller.signal.aborted) {
          setTypes(catalog)
          setPage(record)
        }
      })
      .catch((caught) => {
        if (!controller.signal.aborted) setError(caught.message)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [read, open, attempt])
  async function saved() {
    setEdit(null)
    setValue('')
    setText('')
    setNotice('Change saved with evidence and history.')
    const result = await read()
    setTypes(result.catalog)
    setPage(result.record)
    await onChanged()
  }
  function start(typeId: string, field: TemplateField, previous: Fact | null) {
    setEdit({ typeId, field, previous })
    setValue(previous?.value ?? '')
    setText('')
    setUnknown(previous?.value === null)
    setValidFrom(previous?.valid_from ?? '')
    setValidTo(previous?.valid_to ?? '')
  }
  async function more() {
    if (!page?.next_cursor) return
    setLoading(true)
    setError('')
    try {
      const next = await typeRequest(
        `/assets/${encodeURIComponent(assetId)}?history=${history}&cursor=${encodeURIComponent(page.next_cursor)}`,
        '',
        undefined,
        undefined,
        refreshSession,
      )
      setPage((old) => old && { ...next, facts: [...old.facts, ...next.facts] })
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setLoading(false)
    }
  }
  if (!open)
    return (
      <Button
        variant="outline"
        onClick={() => {
          setLoading(true)
          setError('')
          setOpen(true)
        }}
      >
        Asset type & custom fields
      </Button>
    )
  const assigned = page?.assignments ?? []
  const assignedTypes = types.filter((type) =>
    assigned.some((fact) => fact.value === type.id),
  )
  return (
    <section className="typed-asset" aria-label="Asset type and custom fields">
      <h3>Asset type & custom fields</h3>
      {(error || writer.error) && <p role="alert">{error || writer.error}</p>}
      {notice && <p role="status">{notice}</p>}
      {loading && <p role="status">Loading type details…</p>}
      {error && (
        <Button
          disabled={loading}
          onClick={() => {
            setLoading(true)
            setError('')
            setAttempt((value) => value + 1)
          }}
        >
          Reload type details
        </Button>
      )}
      {assigned.length === 0 && (
        <p>General item. Select a type to add optional fields.</p>
      )}
      {assigned.length > 1 && (
        <p role="status">
          Multiple original type assignments are preserved. Choose the specific
          assignment to correct; values are never merged by type.
        </p>
      )}
      {assigned.map((fact) => (
        <p key={fact.id}>
          Type:{' '}
          <strong>
            {types.find((type) => type.id === fact.value)?.name ?? 'Saved type'}
          </strong>{' '}
          {types.find((type) => type.id === fact.value)?.retired
            ? '(Retired)'
            : ''}
        </p>
      ))}
      <FieldHistory
        entityId={assetId}
        field="profile_asset_type"
        label="Asset type"
        onOpenSource={onEvidence}
      />
      {page && (
        <form
          onSubmit={(event) => {
            event.preventDefault()
            void writer.save(
              '/assign',
              {
                entity_id: assetId,
                type_id: selected,
                replaces_id: replace || null,
                request_id: crypto.randomUUID(),
              },
              saved,
            )
          }}
        >
          <fieldset disabled={frozen}>
            <legend>Assign or change type</legend>
            <label>
              New asset type
              <select
                required
                value={selected}
                onChange={(event) => setSelected(event.target.value)}
              >
                <option value="">Choose a type</option>
                {types
                  .filter((type) => !type.retired)
                  .map((type) => (
                    <option key={type.id} value={type.id}>
                      {type.name}
                    </option>
                  ))}
              </select>
            </label>
            {assigned.length > 0 && (
              <label>
                Assignment to replace
                <select
                  required
                  value={replace}
                  onChange={(event) => setReplace(event.target.value)}
                >
                  <option value="">Choose the previous assignment</option>
                  {assigned.map((fact) => (
                    <option key={fact.id} value={fact.id}>
                      {types.find((type) => type.id === fact.value)?.name ??
                        'Saved type'}{' '}
                      · original {fact.subject_id.slice(0, 8)}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </fieldset>
          <Button type="submit" disabled={writer.busy || Boolean(edit)}>
            {writer.retry && !edit ? 'Retry same change' : 'Save asset type'}
          </Button>
        </form>
      )}
      {!edit &&
        assignedTypes.map((type) => (
          <div key={type.id}>
            <h4>
              {type.name} fields {type.retired ? '(Retired type)' : ''}
            </h4>
            {type.fields.map((field) => {
              const pred =
                field.system_field === 'vin'
                  ? 'profile_vin'
                  : `profile_template_${field.id}`
              const existing = page?.facts.some(
                (fact) => fact.predicate === pred && !fact.superseded_at,
              )
              return (
                <p key={field.id}>
                  {field.name}
                  {field.retired ? ' (Retired)' : ''}
                  {!existing && !field.retired && !type.retired && (
                    <Button
                      variant="outline"
                      disabled={frozen}
                      onClick={() => start(type.id, field, null)}
                    >
                      Add {field.name}
                    </Button>
                  )}
                  {!existing && ' · Unknown / not supplied'}
                </p>
              )
            })}
          </div>
        ))}
      <label>
        <input
          type="checkbox"
          checked={history}
          disabled={frozen || Boolean(edit)}
          onChange={(event) => {
            setLoading(true)
            setError('')
            setHistory(event.target.checked)
          }}
        />{' '}
        Include earlier field statements
      </label>
      <dl>
        {page?.facts.map((fact) => {
          const type = types.find((type) =>
            type.fields.some((field) =>
              field.system_field === 'vin'
                ? fact.predicate === 'profile_vin'
                : fact.predicate === `profile_template_${field.id}`,
            ),
          )
          const field = type?.fields.find((field) =>
            field.system_field === 'vin'
              ? fact.predicate === 'profile_vin'
              : fact.predicate === `profile_template_${field.id}`,
          )
          return (
            <div key={fact.id}>
              <dt>{fact.label ?? field?.name ?? 'Saved custom field'}</dt>
              <dd>
                {fact.value ?? 'Unknown'} · {fact.status}
                {fact.superseded_at ? ' · Earlier statement' : ''}
                {fact.evidence.map((evidence) => (
                  <Button
                    key={evidence.source_id}
                    variant="link"
                    onClick={() => void onEvidence(evidence.source_id)}
                  >
                    View field evidence
                  </Button>
                ))}
                {fact.more_evidence && (
                  <p>More source links are available in field history.</p>
                )}
                {!fact.superseded_at && (
                  <FieldHistory
                    entityId={assetId}
                    field={fact.predicate}
                    label={fact.label ?? field?.name ?? undefined}
                    onOpenSource={onEvidence}
                  />
                )}
                {!fact.superseded_at && type && field && (
                  <Button
                    variant="outline"
                    disabled={frozen || Boolean(edit)}
                    onClick={() => start(type.id, field, fact)}
                  >
                    Correct {fact.label ?? field.name}
                  </Button>
                )}
              </dd>
            </div>
          )
        })}
      </dl>
      {page?.next_cursor && (
        <Button disabled={loading || frozen} onClick={() => void more()}>
          More field statements
        </Button>
      )}
      {edit && (
        <form
          onSubmit={(event) => {
            event.preventDefault()
            void writer.save(
              '/fields',
              {
                entity_id: assetId,
                type_id: edit.typeId,
                field_id: edit.field.id,
                replaces_id: edit.previous?.id ?? null,
                value: unknown ? null : value,
                valid_from: validFrom || null,
                valid_to: validTo || null,
                text,
                request_id: crypto.randomUUID(),
              },
              saved,
            )
          }}
        >
          <fieldset disabled={frozen}>
            <legend>
              {edit.previous ? 'Correct' : 'Add'} {edit.field.name}
            </legend>
            <label>
              Field value
              <input
                maxLength={500}
                required={!unknown}
                disabled={unknown}
                value={value}
                onChange={(event) => setValue(event.target.value)}
              />
            </label>
            <label>
              <input
                type="checkbox"
                checked={unknown}
                onChange={(event) => setUnknown(event.target.checked)}
              />{' '}
              Value is unknown
            </label>
            <label>
              Evidence or your statement
              <textarea
                required
                maxLength={2000}
                value={text}
                onChange={(event) => setText(event.target.value)}
              />
            </label>
            <label>
              Valid from (optional)
              <input
                type="date"
                value={validFrom}
                onChange={(event) => setValidFrom(event.target.value)}
              />
            </label>
            <label>
              Valid until (optional, exclusive)
              <input
                type="date"
                value={validTo}
                onChange={(event) => setValidTo(event.target.value)}
              />
            </label>
            <p>
              Include the exact value in your statement. Corrections preserve
              earlier statements and sources.
            </p>
          </fieldset>
          <Button type="submit" disabled={writer.busy}>
            {writer.retry ? 'Retry same change' : 'Save field statement'}
          </Button>
          <Button
            type="button"
            variant="ghost"
            disabled={frozen}
            onClick={() => setEdit(null)}
          >
            Cancel field edit
          </Button>
        </form>
      )}
      <Button
        variant="ghost"
        disabled={frozen || Boolean(edit)}
        onClick={() => setOpen(false)}
      >
        Close type details
      </Button>
    </section>
  )
}
