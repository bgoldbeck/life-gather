import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import './field-history.css'
import { factLabel } from './profileFields'

type Origin = {
  interface: string
  initiator: string
  method: string
  provider: string | null
  model: string | null
}
type Version = {
  display_value?: string | null
  id: string
  value: unknown
  object_id: string | null
  status: string
  recorded_at: number
  valid_from: string | null
  valid_to: string | null
  superseded_at: number | null
  previous: { value: unknown; object_id: string | null } | null
  origin: Origin | null
  proposal_origin?: Origin | null
  more_evidence: boolean
  evidence: {
    source_id: string
    quote: string
    quote_truncated: boolean
    source_type: string
    source_origin: Origin | null
  }[]
}
type Page = { items: Version[]; next_cursor: string | null }
const words = (value: string) => value.replaceAll('_', ' ')
function attribution(origin: Origin | null) {
  if (!origin) return 'Origin not recorded'
  return [
    origin.method === 'unspecified'
      ? 'Origin unspecified'
      : words(origin.method),
    origin.interface,
    words(origin.initiator),
    origin.provider,
    origin.model,
  ]
    .filter(Boolean)
    .join(' · ')
}
function valueText(value: unknown, object: string | null) {
  return object
    ? `Linked record ${object}`
    : value === null
      ? 'Unknown'
      : JSON.stringify(value)
}

type Props = {
  label?: string
  entityId: string
  field: string
  onOpenSource: (id: string) => void
}
export function FieldHistory(props: Props) {
  return (
    <FieldHistoryPage key={`${props.entityId}:${props.field}`} {...props} />
  )
}
function FieldHistoryPage({ entityId, field, label, onOpenSource }: Props) {
  const [page, setPage] = useState<Page | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const controller = useRef<AbortController | null>(null)
  const pageLimit = useRef(5)
  useEffect(() => {
    return () => {
      controller.current?.abort()
      controller.current = null
    }
  }, [])
  async function load() {
    if (controller.current) return
    const pending = new AbortController()
    controller.current = pending
    setBusy(true)
    setError('')
    try {
      const params = new URLSearchParams({
        entity_id: entityId,
        field,
        limit: String(pageLimit.current),
        cursor: page?.next_cursor ?? '',
      })
      const options = {
        credentials: 'same-origin',
        cache: 'no-store',
        signal: pending.signal,
      } as const
      let response = await fetch(`/api/history/fields?${params}`, options)
      if (response.status === 400 && pageLimit.current !== 1) {
        const failure = (await response.json()) as { detail?: string }
        if (failure.detail?.includes('request a smaller page')) {
          pageLimit.current = 1
          params.set('limit', '1')
          response = await fetch(`/api/history/fields?${params}`, options)
        }
      }
      if (!response.ok) throw new Error('history unavailable')
      const next = (await response.json()) as Page
      if (!pending.signal.aborted)
        setPage((current) => ({
          ...next,
          items: [
            ...new Map(
              [...(current?.items ?? []), ...next.items].map((item) => [
                item.id,
                item,
              ]),
            ).values(),
          ],
        }))
    } catch {
      if (!pending.signal.aborted)
        setError('Unable to load field history. Try again.')
    } finally {
      if (!pending.signal.aborted) {
        controller.current = null
        setBusy(false)
      }
    }
  }
  return (
    <section
      className="field-history"
      aria-label={`${label ?? factLabel(field)} change history`}
    >
      {(!page || page.next_cursor) && (
        <Button variant="outline" disabled={busy} onClick={() => void load()}>
          {busy
            ? 'Loading field history…'
            : page
              ? 'More field changes'
              : `View ${label ?? factLabel(field)} history`}
        </Button>
      )}
      {error && <p role="alert">{error}</p>}
      {page && !page.items.length && (
        <p>No recorded versions for this field.</p>
      )}
      {page && (
        <ol>
          {page.items.map((item) => (
            <li key={item.id}>
              <p>
                {item.previous && (
                  <>
                    {valueText(item.previous.value, item.previous.object_id)}{' '}
                    →{' '}
                  </>
                )}
                {valueText(item.display_value ?? item.value, item.object_id)}
              </p>
              <p>{attribution(item.origin)}</p>
              {item.proposal_origin && (
                <p>Original suggestion: {attribution(item.proposal_origin)}</p>
              )}
              <p>
                Statement status: {item.status} ·{' '}
                {item.superseded_at === null
                  ? 'Current version of this statement'
                  : 'Superseded version'}
              </p>
              <p>
                Recorded {new Date(item.recorded_at / 1000).toLocaleString()} ·
                Valid {item.valid_from ?? 'unknown'} to{' '}
                {item.valid_to ?? 'unknown or open-ended'}
              </p>
              {item.evidence.map((evidence, index) => (
                <div key={`${evidence.source_id}-${index}`}>
                  <p>
                    Source: {words(evidence.source_type)} ·{' '}
                    {attribution(evidence.source_origin)}
                  </p>
                  {evidence.quote && (
                    <blockquote>
                      {evidence.quote}
                      {evidence.quote_truncated && '… (excerpt shortened)'}
                    </blockquote>
                  )}
                  <Button
                    variant="outline"
                    onClick={() => onOpenSource(evidence.source_id)}
                  >
                    Open history evidence {index + 1}
                  </Button>
                </div>
              ))}
              {item.more_evidence && (
                <p>
                  Additional evidence is available in the record’s evidence
                  view.
                </p>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
