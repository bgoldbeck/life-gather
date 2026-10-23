import { useEffect, useRef, useState } from 'react'

export type TemplateField = {
  id: string | null
  name: string
  system_field: 'vin' | null
  retired: boolean
}
export type AssetType = {
  id: string
  name: string
  description: string
  retired: boolean
  revision: string
  seed_key: string | null
  fields: TemplateField[]
}
export type TypeValue = { field_id: string; value: string; text: string }

class TypeRequestError extends Error {
  uncertain: boolean
  constructor(message: string, uncertain: boolean) {
    super(message)
    this.uncertain = uncertain
  }
}

export async function typeRequest(
  path: string,
  csrfToken: string,
  body?: object,
  signal?: AbortSignal,
  refreshSession?: () => Promise<void>,
) {
  let response: Response
  try {
    response = await fetch('/api/asset-types' + path, {
      method: body ? 'POST' : 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      signal,
      headers: body
        ? { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken }
        : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new TypeRequestError(
      body
        ? 'The save result is uncertain. Retry the same change.'
        : 'Unable to load asset types. Try again.',
      Boolean(body),
    )
  }
  if (response.status === 401) await refreshSession?.()
  if (!response.ok) {
    const uncertain = Boolean(body && response.status >= 500)
    let message = uncertain
      ? 'The save result is uncertain. Retry the same change.'
      : 'Unable to complete the change. Reload the latest definition and try again.'
    try {
      const failure = await response.json()
      if (typeof failure.detail === 'string' && !uncertain)
        message = failure.detail
    } catch {
      /* keep bounded message */
    }
    throw new TypeRequestError(message, uncertain)
  }
  try {
    return await response.json()
  } catch {
    throw new TypeRequestError(
      body
        ? 'The save result is uncertain. Retry the same change.'
        : 'Unable to read the asset type response.',
      Boolean(body),
    )
  }
}

export async function typeCatalog(
  includeRetired: boolean,
  signal?: AbortSignal,
  refreshSession?: () => Promise<void>,
): Promise<AssetType[]> {
  const items: AssetType[] = []
  let cursor = ''
  for (let pageNumber = 0; pageNumber < 50; pageNumber++) {
    const suffix = includeRetired ? '?include_retired=true' : ''
    const page = await typeRequest(
      suffix +
        (cursor
          ? `${suffix ? '&' : '?'}cursor=${encodeURIComponent(cursor)}`
          : ''),
      '',
      undefined,
      signal,
      refreshSession,
    )
    items.push(...page.items)
    if (!page.next_cursor) return items
    cursor = page.next_cursor
  }
  throw new Error('Asset type catalog exceeded its page limit.')
}

export function useTypeWrite(
  csrfToken: string,
  refreshSession?: () => Promise<void>,
) {
  const [busy, setBusy] = useState(false)
  const [retry, setRetry] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef<{ path: string; body: object } | null>(null)
  const working = useRef(false)
  const alive = useRef(true)
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])
  async function save(
    path: string,
    body: object,
    onSaved: () => Promise<void>,
  ) {
    if (working.current) return
    working.current = true
    const command = pending.current ?? { path, body }
    pending.current = command
    setBusy(true)
    setError('')
    try {
      await typeRequest(
        command.path,
        csrfToken,
        command.body,
        undefined,
        refreshSession,
      )
      pending.current = null
      if (alive.current) {
        setRetry(false)
        await onSaved()
      }
    } catch (caught) {
      if (!(caught instanceof TypeRequestError && caught.uncertain))
        pending.current = null
      if (alive.current) {
        setRetry(Boolean(pending.current))
        setError((caught as Error).message)
      }
    } finally {
      working.current = false
      if (alive.current) setBusy(false)
    }
  }
  return { save, busy, retry, error }
}

// Loads the active asset types once the add-asset form opens, so the type
// dropdown is a single stable control from the start.
export function useAssetTypeCatalog(refreshSession?: () => Promise<void>) {
  const [items, setItems] = useState<AssetType[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
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
  }, [attempt, refreshSession])
  function reload() {
    setLoading(true)
    setError('')
    setAttempt((value) => value + 1)
  }
  return { items, error, loading, reload }
}

export function activeFields(type: AssetType | null) {
  return (type?.fields ?? []).filter((field) => !field.retired && field.id)
}

export function typeValues(
  type: AssetType | null,
  values: Record<string, string>,
): TypeValue[] {
  return activeFields(type)
    .filter((field) => values[field.id!]?.trim())
    .map((field) => ({
      field_id: field.id!,
      value: values[field.id!].trim(),
      text: `I state ${field.name}: ${values[field.id!].trim()}`,
    }))
}
