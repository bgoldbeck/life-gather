import { useState } from 'react'
import { Button } from '@/components/ui/button'

type Item = { id: string; label: string; updated_at: number }
type Kind = 'photos' | 'documents'

const MAX = 50
const NOUN = { photos: 'photo', documents: 'document' } as const

export function BulkDelete({
  kind,
  items,
  request,
  disabled = false,
  onDeleted,
}: {
  kind: Kind
  items: Item[]
  request: (path: string, init?: RequestInit) => Promise<unknown>
  disabled?: boolean
  onDeleted: (ids: string[]) => Promise<void> | void
}) {
  const [chosen, setChosen] = useState<string[]>([])
  const [acknowledged, setAcknowledged] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const noun = NOUN[kind]
  const visible = chosen.filter((id) => items.some((item) => item.id === id))
  function toggle(id: string, on: boolean) {
    setStatus('')
    setChosen((current) =>
      on
        ? [...current.filter((value) => value !== id), id].slice(0, MAX)
        : current.filter((value) => value !== id),
    )
  }
  async function remove() {
    if (busy || !acknowledged || !visible.length) return
    setBusy(true)
    setError('')
    setStatus('')
    const key = kind === 'photos' ? 'photo_id' : 'document_id'
    try {
      await request(`${kind}/delete-many`, {
        method: 'POST',
        body: JSON.stringify({
          [kind]: visible.map((id) => ({
            [key]: id,
            expected_updated_at: items.find((item) => item.id === id)!
              .updated_at,
          })),
        }),
      })
      setChosen([])
      setAcknowledged(false)
      setStatus(
        `${visible.length} ${noun}(s) deleted. Saved memories and their history remain.`,
      )
      await onDeleted(visible)
    } catch {
      setError(
        `Unable to delete. Nothing was deleted. Reload if a ${noun} changed, then retry.`,
      )
    } finally {
      setBusy(false)
    }
  }
  if (!items.length && !status) return null
  return (
    <details className="bulk-delete">
      <summary>Delete several {noun}s</summary>
      <p>
        Choose up to {MAX}. Each original file and its stored copies are deleted
        permanently, together or not at all. Reviewed text, facts and their
        history stay in memory.
      </p>
      {error && <p role="alert">{error}</p>}
      {status && <p role="status">{status}</p>}
      <fieldset disabled={busy || disabled}>
        <legend>{`Choose ${noun}s to delete`}</legend>
        {items.map((item) => (
          <label key={item.id}>
            <input
              type="checkbox"
              checked={visible.includes(item.id)}
              onChange={(e) => toggle(item.id, e.target.checked)}
            />
            {item.label}
          </label>
        ))}
      </fieldset>
      <label>
        <input
          type="checkbox"
          checked={acknowledged}
          onChange={(e) => setAcknowledged(e.target.checked)}
          disabled={busy || disabled}
        />
        I understand these originals cannot be recovered here
      </label>
      <Button
        variant="outline"
        disabled={busy || disabled || !acknowledged || !visible.length}
        onClick={() => void remove()}
      >
        {`Delete ${visible.length} selected permanently`}
      </Button>
    </details>
  )
}
