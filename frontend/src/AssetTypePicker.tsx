import { Button } from '@/components/ui/button'
import {
  activeFields,
  type AssetType,
  type useAssetTypeCatalog,
} from './assetTypes'

export function AssetTypeSelect({
  catalog,
  disabled,
  value,
  onChange,
}: {
  catalog: ReturnType<typeof useAssetTypeCatalog>
  disabled: boolean
  value: string
  onChange: (id: string) => void
}) {
  return (
    <div className="manual-asset-type">
      <label>
        Asset type
        <select
          disabled={disabled || catalog.loading}
          value={value}
          aria-describedby="manual-asset-type-hint"
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">General item</option>
          {catalog.items.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      {catalog.error ? (
        <p role="alert" className="manual-asset-hint">
          {catalog.error}{' '}
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={disabled}
            onClick={catalog.reload}
          >
            Retry loading types
          </Button>
        </p>
      ) : (
        <p id="manual-asset-type-hint" className="manual-asset-hint">
          {catalog.loading
            ? 'Loading asset types…'
            : 'Adds detail fields for that kind of item.'}
        </p>
      )}
    </div>
  )
}

export function AssetTypeDetails({
  type,
  disabled,
  values,
  onChange,
}: {
  type: AssetType | null
  disabled: boolean
  values: Record<string, string>
  onChange: (fieldId: string, value: string) => void
}) {
  const fields = activeFields(type)
  if (!type || !fields.length) return null
  return (
    <fieldset className="manual-asset-type-details">
      <legend>{type.name} details</legend>
      <p className="manual-asset-hint">
        {type.description ||
          'Optional. Saved as your statements. Leave unknown values blank and include units where relevant.'}
      </p>
      {fields.map((field) => (
        <label key={field.id}>
          {field.name}
          <input
            disabled={disabled}
            maxLength={500}
            value={values[field.id!] ?? ''}
            onChange={(event) => onChange(field.id!, event.target.value)}
          />
        </label>
      ))}
    </fieldset>
  )
}
