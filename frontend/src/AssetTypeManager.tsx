import { useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  typeRequest,
  typeCatalog,
  useTypeWrite,
  type AssetType,
  type TemplateField,
} from './assetTypes'
import './asset-types.css'

type Draft = Omit<AssetType, 'id' | 'revision' | 'seed_key'> & {
  id?: string
  revision?: string
}
const blank = (): Draft => ({
  name: '',
  description: '',
  retired: false,
  fields: [],
})

export function AssetTypeManager({
  csrfToken,
  refreshSession,
}: {
  csrfToken: string
  refreshSession?: () => Promise<void>
}) {
  const [items, setItems] = useState<AssetType[]>([])
  const [draft, setDraft] = useState<Draft | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [attempt, setAttempt] = useState(0)
  const [notice, setNotice] = useState('')
  const [history, setHistory] = useState<{
    items: { id: string; recorded_at: number | null; definition: AssetType }[]
    next_cursor: string | null
  } | null>(null)
  const [historyType, setHistoryType] = useState('')
  const writer = useTypeWrite(csrfToken, refreshSession)
  const load = useCallback(
    async (signal?: AbortSignal) => {
      const items = await typeCatalog(true, signal, refreshSession)
      if (!signal?.aborted) setItems(items)
    },
    [refreshSession],
  )
  useEffect(() => {
    const controller = new AbortController()
    void typeCatalog(true, controller.signal, refreshSession)
      .then((items) => {
        if (!controller.signal.aborted) setItems(items)
      })
      .catch((caught) => {
        if (!controller.signal.aborted) setError(caught.message)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [refreshSession, attempt])
  const frozen = writer.busy || writer.retry
  function field(index: number, changes: Partial<TemplateField>) {
    setDraft(
      (old) =>
        old && {
          ...old,
          fields: old.fields.map((item, position) =>
            position === index ? { ...item, ...changes } : item,
          ),
        },
    )
  }
  function move(index: number, direction: number) {
    if (!draft) return
    const fields = [...draft.fields]
    ;[fields[index], fields[index + direction]] = [
      fields[index + direction],
      fields[index],
    ]
    setDraft({ ...draft, fields })
  }
  async function showHistory(id: string, cursor = '') {
    setError('')
    try {
      const page = await typeRequest(
        `/${encodeURIComponent(id)}/history${cursor ? '?cursor=' + encodeURIComponent(cursor) : ''}`,
        '',
        undefined,
        undefined,
        refreshSession,
      )
      setHistory((old) =>
        cursor && old
          ? { ...page, items: [...old.items, ...page.items] }
          : page,
      )
      setHistoryType(id)
    } catch (caught) {
      setError((caught as Error).message)
    }
  }
  return (
    <section className="asset-types" aria-label="Manage asset types">
      <h2>Asset types</h2>
      <p>
        These private forms describe your items. Editing a type never invents
        values or changes another account. Retire fields to preserve their
        existing data.
      </p>
      {(error || writer.error) && <p role="alert">{error || writer.error}</p>}
      {notice && <p role="status">{notice}</p>}
      {loading && <p role="status">Loading asset types…</p>}
      {error && (
        <Button
          onClick={() => {
            setLoading(true)
            setError('')
            setAttempt((value) => value + 1)
          }}
        >
          Reload types
        </Button>
      )}
      {!draft && (
        <>
          <Button
            onClick={() => {
              setDraft(blank())
              setNotice('')
            }}
          >
            Create asset type
          </Button>
          <ul className="type-catalog">
            {items.map((item) => (
              <li key={item.id}>
                <strong>{item.name}</strong>{' '}
                {item.retired
                  ? 'Retired'
                  : item.seed_key
                    ? 'Editable starter'
                    : 'Custom'}
                <p>
                  {item.description ||
                    `${item.fields.filter((field) => !field.retired).length} optional fields`}
                </p>
                <Button
                  variant="outline"
                  onClick={() => {
                    setDraft(structuredClone(item))
                    setNotice('')
                  }}
                >
                  Edit {item.name}
                </Button>
                <Button
                  variant="outline"
                  onClick={() =>
                    setDraft({
                      ...blank(),
                      name: item.name + ' copy',
                      description: item.description,
                      fields: item.fields
                        .filter((field) => !field.retired)
                        .map((field) => ({ ...field, id: null })),
                    })
                  }
                >
                  Copy {item.name}
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => void showHistory(item.id)}
                >
                  History of {item.name}
                </Button>
              </li>
            ))}
          </ul>
        </>
      )}
      {draft && (
        <form
          onSubmit={(event) => {
            event.preventDefault()
            void writer.save(
              '',
              {
                type_id: draft.id ?? null,
                expected_revision: draft.revision ?? null,
                request_id: crypto.randomUUID(),
                name: draft.name,
                description: draft.description,
                retired: draft.retired,
                fields: draft.fields,
              },
              async () => {
                setDraft(null)
                setNotice(
                  'Asset type saved. Existing values and history are preserved.',
                )
                await load()
              },
            )
          }}
        >
          <fieldset disabled={frozen}>
            <legend>{draft.id ? 'Edit type' : 'Create type'}</legend>
            <label>
              Type name
              <input
                required
                maxLength={80}
                value={draft.name}
                onChange={(event) =>
                  setDraft({ ...draft, name: event.target.value })
                }
              />
            </label>
            <label>
              Type description
              <textarea
                maxLength={500}
                value={draft.description}
                onChange={(event) =>
                  setDraft({ ...draft, description: event.target.value })
                }
              />
            </label>
            <label>
              <input
                type="checkbox"
                checked={draft.retired}
                onChange={(event) =>
                  setDraft({ ...draft, retired: event.target.checked })
                }
              />
              Retire this type from new entry
            </label>
            {draft.fields.map((item, index) => (
              <div className="template-field" key={item.id ?? `new-${index}`}>
                <label>
                  Field {index + 1} name
                  <input
                    required
                    maxLength={48}
                    readOnly={Boolean(item.system_field)}
                    value={item.name}
                    onChange={(event) =>
                      field(index, { name: event.target.value })
                    }
                  />
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={item.retired}
                    onChange={(event) =>
                      field(index, { retired: event.target.checked })
                    }
                  />
                  Retire field {index + 1}
                </label>
                <Button
                  type="button"
                  variant="outline"
                  disabled={!index}
                  onClick={() => move(index, -1)}
                  aria-label={`Move field ${index + 1} up`}
                >
                  Up
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={index === draft.fields.length - 1}
                  onClick={() => move(index, 1)}
                  aria-label={`Move field ${index + 1} down`}
                >
                  Down
                </Button>
                {!item.id && (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() =>
                      setDraft({
                        ...draft,
                        fields: draft.fields.filter(
                          (_, position) => position !== index,
                        ),
                      })
                    }
                  >
                    Remove new field {index + 1}
                  </Button>
                )}
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              disabled={draft.fields.length >= 32}
              onClick={() =>
                setDraft({
                  ...draft,
                  fields: [
                    ...draft.fields,
                    { id: null, name: '', system_field: null, retired: false },
                  ],
                })
              }
            >
              Add field
            </Button>
          </fieldset>
          <p>
            All fields are optional text. Include units in values. Use the
            shared manufacturer/model/serial and purchase evidence controls for
            those details. VIN keeps its standard meaning.
          </p>
          <Button type="submit" disabled={writer.busy}>
            {writer.retry
              ? 'Retry same change'
              : writer.busy
                ? 'Saving…'
                : 'Save type'}
          </Button>
          <Button
            type="button"
            variant="ghost"
            disabled={frozen}
            onClick={() => setDraft(null)}
          >
            Cancel type edit
          </Button>
        </form>
      )}
      {history && (
        <section aria-label="Type definition history">
          <h3>Definition history</h3>
          <p>
            Names below were recorded in each definition; saved asset evidence
            remains unchanged.
          </p>
          {history.items.map((row) => (
            <details key={row.id}>
              <summary>
                {row.definition.name} ·{' '}
                {row.recorded_at
                  ? new Date(row.recorded_at / 1000).toLocaleString()
                  : 'Starter definition'}
              </summary>
              <p>
                {row.definition.description}{' '}
                {row.definition.retired ? '(Retired)' : ''}
              </p>
              <ul>
                {row.definition.fields.map((field) => (
                  <li key={field.id}>
                    {field.name}
                    {field.retired ? ' (Retired)' : ''}
                  </li>
                ))}
              </ul>
            </details>
          ))}
          {history.next_cursor && (
            <Button
              onClick={() =>
                void showHistory(historyType, history.next_cursor!)
              }
            >
              More definition history
            </Button>
          )}
          <Button variant="ghost" onClick={() => setHistory(null)}>
            Close definition history
          </Button>
        </section>
      )}
    </section>
  )
}
