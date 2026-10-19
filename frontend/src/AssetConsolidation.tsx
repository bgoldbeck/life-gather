import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import type { Comparison } from './RecordComparison'

type RecordChoice = { id: string; name: string }
export type Consolidation = {
  id: string
  primary_id: string
  secondary_id: string
  source_id: string
  recorded_at: number
}

export function AssetConsolidation({
  records = [],
  consolidation,
  csrfToken,
  onPreview,
  onPending,
  onChanged,
}: {
  records?: RecordChoice[]
  consolidation?: Consolidation
  csrfToken: string
  onPreview?: (value: Comparison) => void
  onPending?: (pending: boolean) => void
  onChanged: (id: string) => Promise<void>
}) {
  const [primary, setPrimary] = useState(records[0]?.id ?? '')
  const [token, setToken] = useState('')
  const [note, setNote] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [uncertain, setUncertain] = useState(false)
  const [saved, setSaved] = useState(false)
  const [previewCounts, setPreviewCounts] = useState<{
    [key: string]: number
  } | null>(null)
  const pending = useRef<{ path: string; body: string } | null>(null)
  const active = useRef(true)
  const working = useRef(false)
  const generation = useRef(0)
  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
    }
  }, [])

  const reverse = Boolean(consolidation)
  const locked = busy || uncertain || saved

  async function preview() {
    if (working.current || locked) return
    working.current = true
    const version = ++generation.current
    setBusy(true)
    setError('')
    setToken('')
    setPreviewCounts(null)
    setConfirmed(false)
    onPending?.(true)
    try {
      const response = await fetch('/api/assets/consolidation/preview', {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify({
          primary_id: primary,
          secondary_id: records.find((row) => row.id !== primary)?.id,
        }),
      })
      const value = await response.json()
      if (!response.ok)
        throw new Error(
          typeof value.detail === 'string'
            ? value.detail
            : 'Unable to preview these records.',
        )
      if (!active.current || version !== generation.current) return
      if (
        !value.comparison?.complete ||
        typeof value.preview_token !== 'string' ||
        !/^[a-f0-9]{64}$/.test(value.preview_token)
      )
        throw new Error('A complete current preview is required.')
      setToken(value.preview_token)
      setPreviewCounts(value.comparison.counts)
      onPreview?.(value.comparison as Comparison)
    } catch (caught) {
      if (active.current && version === generation.current)
        setError((caught as Error).message)
    } finally {
      working.current = false
      if (active.current && version === generation.current) {
        setBusy(false)
        onPending?.(false)
      }
    }
  }

  async function reload(id: string) {
    try {
      await onChanged(id)
    } catch {
      if (active.current)
        setError(
          'The change is saved. Reload the record to see its current details.',
        )
    }
  }

  async function write() {
    if (
      working.current ||
      saved ||
      (!pending.current && (!confirmed || !note.trim() || (!reverse && !token)))
    )
      return
    if (!pending.current) {
      pending.current = {
        path: reverse ? 'reverse' : 'apply',
        body: JSON.stringify(
          reverse
            ? {
                consolidation_id: consolidation!.id,
                request_id: crypto.randomUUID(),
                note,
              }
            : {
                primary_id: primary,
                secondary_id: records.find((row) => row.id !== primary)?.id,
                preview_token: token,
                request_id: crypto.randomUUID(),
                note,
                same_item_confirmed: confirmed,
              },
        ),
      }
    }
    working.current = true
    setBusy(true)
    setError('')
    onPending?.(true)
    try {
      const response = await fetch(
        '/api/assets/consolidation/' + pending.current.path,
        {
          method: 'POST',
          credentials: 'same-origin',
          cache: 'no-store',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrfToken,
          },
          body: pending.current.body,
        },
      )
      if (!active.current) return
      if (response.status >= 400 && response.status < 500) {
        pending.current = null
        setUncertain(false)
        setToken('')
        setPreviewCounts(null)
        onPending?.(false)
        const value = await response.json()
        throw new Error(
          typeof value.detail === 'string'
            ? value.detail
            : 'The records changed or access expired. Review them again.',
        )
      }
      if (!response.ok)
        throw new Error('The result is uncertain. Retry the same request.')
      const value = await response.json()
      if (!active.current) return
      if (typeof value.id !== 'string' || typeof value.primary_id !== 'string')
        throw new Error('The result is uncertain. Retry the same request.')
      setSaved(true)
      setUncertain(false)
      pending.current = null
      onPending?.(false)
      await reload(value.primary_id)
    } catch (caught) {
      if (active.current) {
        setUncertain(Boolean(pending.current))
        setError((caught as Error).message || 'Unable to complete the change.')
      }
    } finally {
      working.current = false
      if (active.current) setBusy(false)
    }
  }

  return (
    <section
      className="consolidation"
      aria-label={
        reverse ? 'Reverse consolidation' : 'Consolidate these records'
      }
    >
      <h3>{reverse ? 'Consolidated item' : 'Consolidate these records'}</h3>
      <p>
        {reverse
          ? 'Both original records and their evidence are preserved. Reversal separates unchanged records; later dependent changes require inspection first.'
          : 'Only confirm when both records describe the same physical item. Keep conflicting statements and original sources; purchase totals are never added together.'}
      </p>
      {!reverse && (
        <>
          <label>
            Primary record
            <select
              value={primary}
              disabled={locked}
              onChange={(event) => {
                ++generation.current
                setPrimary(event.target.value)
                setToken('')
                setPreviewCounts(null)
                setConfirmed(false)
              }}
            >
              {records.map((record) => (
                <option key={record.id} value={record.id}>
                  {record.name} · {record.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
          <Button
            variant="outline"
            disabled={locked || records.length !== 2}
            onClick={() => void preview()}
          >
            Preview consolidation
          </Button>
          {previewCounts && (
            <p role="status">
              Fresh complete preview:{' '}
              {Object.entries(previewCounts)
                .map(([name, count]) => `${count} ${name.replaceAll('_', ' ')}`)
                .join(', ')}
              . Inspect the comparison below before confirming.
            </p>
          )}
        </>
      )}
      <label>
        Explanation
        <textarea
          value={note}
          maxLength={2000}
          disabled={locked}
          onChange={(event) => setNote(event.target.value)}
        />
      </label>
      <label>
        <input
          type="checkbox"
          checked={confirmed}
          disabled={locked}
          onChange={(event) => setConfirmed(event.target.checked)}
        />
        {reverse
          ? 'I want to separate these records.'
          : 'I confirm these records describe the same physical item.'}
      </label>
      {!saved && (
        <Button
          disabled={
            busy ||
            (!uncertain && (!confirmed || !note.trim() || (!reverse && !token)))
          }
          onClick={() => void write()}
        >
          {busy
            ? 'Saving…'
            : uncertain
              ? 'Retry same request'
              : reverse
                ? 'Reverse consolidation'
                : 'Confirm consolidation'}
        </Button>
      )}
      {uncertain && (
        <p role="status">
          Keep this selection while retrying. The same request cannot apply the
          change twice.
        </p>
      )}
      {saved && (
        <>
          <p role="status">The change is saved.</p>
          <Button
            variant="outline"
            onClick={() => void reload(consolidation?.primary_id ?? primary)}
          >
            Reload record
          </Button>
        </>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  )
}
