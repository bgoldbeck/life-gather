import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { typeCatalog, type AssetType, type TypeValue } from './assetTypes'

export function AssetTypePicker({
  disabled,
  onChange,
  refreshSession,
}: {
  disabled: boolean
  onChange: (type: AssetType | null, values: TypeValue[]) => void
  refreshSession?: () => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<AssetType[]>([])
  const [selected, setSelected] = useState('')
  const [values, setValues] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    void typeCatalog(false, controller.signal, refreshSession)
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
  }, [open, attempt, refreshSession])
  const template = items.find((item) => item.id === selected) ?? null
  function change(type: AssetType | null, next: Record<string, string>) {
    onChange(
      type,
      (type?.fields ?? [])
        .filter((field) => !field.retired && field.id && next[field.id]?.trim())
        .map((field) => ({
          field_id: field.id!,
          value: next[field.id!].trim(),
          text: `I state ${field.name}: ${next[field.id!].trim()}`,
        })),
    )
  }
  if (!open)
    return (
      <p>
        Asset type: General item{' '}
        <Button
          type="button"
          variant="outline"
          disabled={disabled}
          onClick={() => {
            setLoading(true)
            setError('')
            setOpen(true)
          }}
        >
          Choose asset type
        </Button>
      </p>
    )
  return (
    <div className="asset-type-fields">
      {loading && <p role="status">Loading asset types…</p>}
      {error && (
        <p role="alert">
          {error}{' '}
          <Button
            type="button"
            disabled={disabled || loading}
            onClick={() => {
              setLoading(true)
              setError('')
              setAttempt((value) => value + 1)
            }}
          >
            Retry loading types
          </Button>
        </p>
      )}
      <label>
        Asset type
        <select
          disabled={disabled || loading}
          value={selected}
          onChange={(event) => {
            setSelected(event.target.value)
            setValues({})
            change(
              items.find((item) => item.id === event.target.value) ?? null,
              {},
            )
          }}
        >
          <option value="">General item</option>
          {items.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      {template && (
        <>
          <p>
            {template.description ||
              'Optional details are saved as your statements. Leave unknown values blank; include units where relevant.'}
          </p>
          {template.fields
            .filter((field) => !field.retired)
            .map((field) => (
              <label key={field.id}>
                {field.name}
                <input
                  disabled={disabled}
                  maxLength={500}
                  value={values[field.id!] ?? ''}
                  onChange={(event) => {
                    const next = { ...values, [field.id!]: event.target.value }
                    setValues(next)
                    change(template, next)
                  }}
                />
              </label>
            ))}
        </>
      )}
      <p>Create or edit types using Manage asset types on Assets.</p>
    </div>
  )
}
