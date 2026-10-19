export const profileFields = [
  'manufacturer',
  'model',
  'serial',
  'vin',
  'filter_dimensions',
  'paint',
  'maintenance',
  'specification',
] as const

const reserved = new Set<string>([...profileFields, 'kind', 'profile_kind'])
const customPrefix = 'profile_custom_'

export function customProfileName(name: string): string | null {
  const trimmed = name.trim()
  if (
    trimmed.length > 48 ||
    !/^[A-Za-z0-9]+(?:[ _-]+[A-Za-z0-9]+)*$/.test(trimmed)
  )
    return null
  const normalized = trimmed.replace(/[ _-]+/g, '_').toLowerCase()
  return reserved.has(normalized) ? null : normalized
}

export function editableProfileField(predicate: string): {
  field: (typeof profileFields)[number] | 'custom'
  customName: string
} | null {
  if (predicate.startsWith(customPrefix)) {
    const name = predicate.slice(customPrefix.length)
    if (customProfileName(name) === name)
      return { field: 'custom', customName: name.replaceAll('_', ' ') }
  }
  const field = profileFields.find((name) => predicate === `profile_${name}`)
  return field ? { field, customName: '' } : null
}

export function customDetailLabel(predicate: string): string {
  const editable = editableProfileField(predicate)
  return editable?.field === 'custom' ? editable.customName : predicate
}

export function factLabel(predicate: string): string {
  return customDetailLabel(predicate).replaceAll('_', ' ')
}

export function profileLabel(predicate: string): string {
  return predicate.startsWith(customPrefix)
    ? factLabel(predicate)
    : predicate.replace(/^profile_/, '').replaceAll('_', ' ')
}
