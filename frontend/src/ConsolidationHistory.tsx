import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'

export type IdentityChoice = {
  id: string
  primary_name: string
  secondary_name: string
  source_id: string
  recorded_at: number
  superseded_at: number | null
  reverse_source_id: string | null
}

export function ConsolidationHistory({
  assetId,
  initial,
  cursor: initialCursor,
  csrfToken,
  onOpen,
}: {
  assetId: string
  initial: IdentityChoice[]
  cursor: string | null
  csrfToken: string
  onOpen: (id: string) => Promise<void>
}) {
  const [rows, setRows] = useState(initial)
  const [cursor, setCursor] = useState(initialCursor)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const active = useRef(true)
  const working = useRef(false)
  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
    }
  }, [])
  async function more() {
    if (!cursor || working.current) return
    working.current = true
    setBusy(true)
    setError('')
    try {
      const response = await fetch(
        `/api/assets/${encodeURIComponent(assetId)}?identity_cursor=${encodeURIComponent(cursor)}`,
        {
          credentials: 'same-origin',
          cache: 'no-store',
          headers: { 'X-CSRF-Token': csrfToken },
        },
      )
      if (!response.ok) throw new Error('Unable to load consolidation history.')
      const page = await response.json()
      if (!active.current) return
      setRows((current) => [
        ...new Map(
          [...current, ...page.identity_history].map((row: IdentityChoice) => [
            row.id,
            row,
          ]),
        ).values(),
      ])
      setCursor(page.next_identity_cursor)
    } catch {
      if (active.current)
        setError('Unable to load consolidation history. Try again.')
    } finally {
      working.current = false
      if (active.current) setBusy(false)
    }
  }
  return (
    <details className="consolidation-history">
      <summary>Consolidation history</summary>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>
            <p>
              {row.primary_name} + {row.secondary_name} ·{' '}
              {row.superseded_at === null
                ? 'Active identity choice'
                : 'Reversed identity choice'}
            </p>
            <p>Recorded {new Date(row.recorded_at / 1000).toLocaleString()}</p>
            <Button
              variant="outline"
              onClick={() => void onOpen(row.source_id)}
            >
              View identity explanation
            </Button>
            {row.reverse_source_id && (
              <>
                <p>
                  Reversed{' '}
                  {new Date(row.superseded_at! / 1000).toLocaleString()}
                </p>
                <Button
                  variant="outline"
                  onClick={() => void onOpen(row.reverse_source_id!)}
                >
                  View reversal explanation
                </Button>
              </>
            )}
          </li>
        ))}
      </ul>
      {cursor && (
        <Button disabled={busy} variant="outline" onClick={() => void more()}>
          More identity history
        </Button>
      )}
      {error && <p role="alert">{error}</p>}
    </details>
  )
}
