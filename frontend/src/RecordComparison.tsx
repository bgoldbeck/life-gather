import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import './record-comparison.css'
import { AssetConsolidation } from './AssetConsolidation'
import { customDetailLabel } from './profileFields'

type Record = {
  id: string
  name: string
  source_id: string
  in_inventory?: boolean
}
type Fact = {
  id: string
  subject_id: string
  predicate: string
  object_id: string | null
  value: string | number | boolean | null
  display_value?: string
  status: string
  recorded_at: number
  valid_from: string | null
  valid_to: string | null
  evidence: { source_id: string; quote: string | null }[]
}
export type Comparison = {
  complete: boolean
  records: Record[]
  references?: Record[]
  purchases?: {
    id: string
    retailer: string
    order_id: string
    source_id: string
  }[]
  counts: { [key: string]: number }
  limits?: { [key: string]: number }
  limited_sections: string[]
  source_states?: {
    [key: string]: { is_current: boolean; current_source_id: string }
  }
  warnings: {
    code: string
    message: string
    predicate?: string
    statement_ids?: string[]
  }[]
  sections: {
    maintenance?: {
      id: string
      revision_id: string
      asset_id: string
      title: string
      due_on: string | null
      timezone: string
      state: string
      completed_on: string | null
      source_id: string
      recorded_at: number
    }[]
    statements?: Fact[]
    aliases?: {
      id: string
      asset_id: string
      name: string
      source_id: string
    }[]
    photos?: {
      link_id: string
      asset_id: string
      id: string
      filename: string
      purpose: string
      deleted: boolean
      source_id: string | null
    }[]
    associations?: {
      asset_id: string
      decision_id: string
      observation_id: string
      source_id: string
      unit: number
      quantity: number
      name: string
      serial: string | null
      manufacturer: string | null
      purchase_id: string | null
    }[]
    receipt_lines?: {
      asset_id: string
      key: string
      source_id: string
      name: string
      unit: number
      quantity: number
      source_current: boolean
      claim: null | {
        line_total: string | null
        currency: string | null
        purchase_date: string | null
      }
    }[]
    purchase_evidence?: {
      id: string
      purchase_id: string
      source_id: string
      source_current: boolean
      role: string
      amount_minor: number | null
      currency: string | null
      quote: string
      occurred_on: string | null
    }[]
  }
}
const sectionLabels: { [key: string]: string } = {
  statements: 'Statements and relationships',
  evidence: 'Statement evidence',
  aliases: 'Alternative names',
  photos: 'Gallery links',
  associations: 'Discovery associations',
  purchase_evidence: 'Purchase evidence',
  receipt_lines: 'Receipt lines',
  sources: 'Original sources',
  maintenance: 'Maintenance tasks',
  response_bytes: 'Comparison size',
}

function amount(value: number, currency: string | null) {
  const digits = String(value).padStart(3, '0')
  return `${currency ?? 'Unknown currency'} ${currency === 'JPY' ? value : digits.slice(0, -2) + '.' + digits.slice(-2)}`
}

export function RecordComparison({
  assetId,
  assetName,
  csrfToken,
  onOpen,
  disabled: externallyDisabled = false,
  onConsolidated,
}: {
  assetId: string
  assetName: string
  csrfToken: string
  onOpen: (id: string) => Promise<void>
  disabled?: boolean
  onConsolidated?: (id: string) => Promise<void>
}) {
  const [consolidationPending, setConsolidationPending] = useState(false)
  const disabled = externallyDisabled || consolidationPending
  const [query, setQuery] = useState('')
  const [items, setItems] = useState<Record[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [target, setTarget] = useState('')
  const [result, setResult] = useState<Comparison | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const generation = useRef(0)
  const controller = useRef<AbortController | null>(null)
  useEffect(
    () => () => {
      controller.current?.abort()
    },
    [],
  )
  function clear() {
    ++generation.current
    controller.current?.abort()
    setResult(null)
    setError('')
    setBusy(false)
  }
  async function read(compare: boolean, more = false) {
    const version = ++generation.current
    controller.current?.abort()
    const pending = new AbortController()
    controller.current = pending
    setBusy(true)
    setError('')
    setResult(null)
    try {
      const response = await fetch(
        compare
          ? '/api/assets/comparison'
          : `/api/assets?include_history=true&limit=5&query=${encodeURIComponent(query)}${more ? '&cursor=' + encodeURIComponent(cursor ?? '') : ''}`,
        {
          credentials: 'same-origin',
          cache: 'no-store',
          signal: pending.signal,
          ...(compare
            ? {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  'X-CSRF-Token': csrfToken,
                },
                body: JSON.stringify({
                  asset_id: assetId,
                  target_asset_id: target,
                }),
              }
            : {}),
        },
      )
      if (!response.ok) throw new Error()
      const data = await response.json()
      if (version !== generation.current || pending.signal.aborted) return
      if (compare) setResult(data)
      else {
        setItems((old) => [
          ...(more ? old : []),
          ...data.items.filter((row: Record) => row.id !== assetId),
        ])
        setCursor(data.next_cursor)
        if (!more) setTarget('')
      }
    } catch {
      if (version === generation.current && !pending.signal.aborted)
        setError(
          compare
            ? 'Unable to compare these records. Reload and try again.'
            : 'Unable to find items. Try again.',
        )
    } finally {
      if (version === generation.current && !pending.signal.aborted)
        setBusy(false)
    }
  }
  const names = new Map(
    [...(result?.records ?? []), ...(result?.references ?? [])].map((row) => [
      row.id,
      row.name,
    ]),
  )
  function purchaseLabel(id: string) {
    const purchase = result?.purchases?.find((row) => row.id === id)
    return purchase
      ? `${purchase.retailer} · order ${purchase.order_id}`
      : `purchase ${id.slice(0, 8)}`
  }
  function source(id: string, label = 'View original evidence') {
    const state = result?.source_states?.[id]
    return (
      <span className="comparison-source">
        <Button
          variant="outline"
          disabled={disabled}
          onClick={() => void onOpen(id)}
        >
          {label}
        </Button>
        {state && !state.is_current && (
          <>
            <span>Original source has a later correction.</span>
            <Button
              variant="outline"
              disabled={disabled}
              onClick={() => void onOpen(state.current_source_id)}
            >
              View current source
            </Button>
          </>
        )}
      </span>
    )
  }
  return (
    <section
      className="record-comparison"
      aria-label="Compare complete current records"
    >
      <h3>Compare current records</h3>
      <p>
        Inspect {assetName} beside another item before correcting a possible
        duplicate. Comparison does not decide identity; consolidation requires a
        separate fresh preview and your explicit confirmation.
      </p>
      <label>
        Find another item
        <input
          value={query}
          maxLength={200}
          disabled={disabled}
          onChange={(event) => {
            clear()
            setQuery(event.target.value)
            setTarget('')
            setItems([])
            setCursor(null)
          }}
        />
      </label>
      <Button
        variant="outline"
        disabled={busy || disabled}
        onClick={() => void read(false)}
      >
        Find comparison items
      </Button>
      {items.length > 0 && (
        <label>
          Compare with
          <select
            value={target}
            disabled={disabled || busy}
            onChange={(event) => {
              clear()
              setTarget(event.target.value)
            }}
          >
            <option value="">Choose a distinct item</option>
            {items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} · {item.id.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
      )}
      {cursor && (
        <Button
          variant="outline"
          disabled={disabled || busy}
          onClick={() => void read(false, true)}
        >
          More comparison items
        </Button>
      )}
      <Button
        disabled={disabled || busy || !target}
        onClick={() => void read(true)}
      >
        Compare selected records
      </Button>
      {(busy || result || error) && (
        <Button variant="outline" disabled={disabled} onClick={clear}>
          Clear comparison
        </Button>
      )}
      {busy && <p role="status">Loading current record comparison…</p>}
      {error && <p role="alert">{error}</p>}
      {result && (
        <>
          {result.complete && onConsolidated && (
            <AssetConsolidation
              key={target}
              records={result.records}
              csrfToken={csrfToken}
              onPreview={setResult}
              onPending={setConsolidationPending}
              onChanged={onConsolidated}
            />
          )}
          <p role="status">
            {result.complete
              ? 'Complete within the stated current-version scope.'
              : 'A complete comparison is unavailable. No partial record details are shown.'}
          </p>
          <p>
            Current statement versions, including their known world dates, are
            shown. Older versions, note history and earlier corrections remain
            on the original records. Inventory may be inferred. Similar names do
            not establish identity.
          </p>
          <dl className="comparison-counts">
            {Object.entries(result.counts).map(([key, count]) => (
              <div key={key}>
                <dt>{sectionLabels[key] ?? key}</dt>
                <dd>
                  {!result.complete ? 'At least ' : ''}
                  {count}
                </dd>
                {result.limits?.[key] !== undefined && (
                  <dd>Comparison limit: {result.limits[key]}</dd>
                )}
              </div>
            ))}
          </dl>
          <p>
            Receipt inspection is limited to twenty line associations per item.
            All other limits apply to the pair.
          </p>
          {!result.complete && (
            <p>
              Limit reached:{' '}
              {result.limited_sections
                .map((key) => sectionLabels[key] ?? key)
                .join(', ')}
              . Inspect each record’s existing detail and history views. Nothing
              was changed.
            </p>
          )}
          {result.warnings.length > 0 && (
            <section aria-label="Comparison warnings">
              <h4>Inspect before correcting</h4>
              <ul>
                {result.warnings.map((warning, index) => (
                  <li key={index}>
                    {warning.predicate && (
                      <strong>{customDetailLabel(warning.predicate)}: </strong>
                    )}
                    {warning.message}
                  </li>
                ))}
              </ul>
            </section>
          )}
          {result.complete && (
            <>
              <div className="record-comparison-grid">
                {result.records.map((record) => (
                  <article
                    key={record.id}
                    aria-label={`Current record ${record.name}`}
                  >
                    <h4>{record.name}</h4>
                    <p className="comparison-id">{record.id}</p>
                    <p>
                      {record.in_inventory
                        ? 'In current inventory; ownership may be inferred.'
                        : 'Outside current inventory; inspect ownership statements.'}
                    </p>
                    {source(record.source_id, 'View record original source')}
                    <h5>Alternative names</h5>
                    {!result.sections.aliases?.some(
                      (row) => row.asset_id === record.id,
                    ) && <p>No alternative names recorded.</p>}
                    <ul>
                      {result.sections.aliases
                        ?.filter((row) => row.asset_id === record.id)
                        .map((row) => (
                          <li key={row.id}>
                            {row.name}
                            {source(row.source_id, 'View name evidence')}
                          </li>
                        ))}
                    </ul>
                    <h5>Statements and relationships</h5>
                    {!result.sections.statements?.some(
                      (row) =>
                        row.subject_id === record.id ||
                        row.object_id === record.id,
                    ) && <p>No statements or relationships in this scope.</p>}
                    <ul>
                      {result.sections.statements
                        ?.filter(
                          (row) =>
                            row.subject_id === record.id ||
                            row.object_id === record.id,
                        )
                        .map((fact) => (
                          <li key={fact.id}>
                            <p>
                              {fact.subject_id !== record.id && (
                                <>
                                  {names.get(fact.subject_id) ??
                                    fact.subject_id}{' '}
                                  →{' '}
                                </>
                              )}
                              <strong>
                                {customDetailLabel(fact.predicate)}
                              </strong>
                              :{' '}
                              {fact.object_id
                                ? (names.get(fact.object_id) ?? fact.object_id)
                                : fact.value === null
                                  ? 'Unknown'
                                  : (fact.display_value ??
                                    String(fact.value))}{' '}
                              · {fact.status}
                            </p>
                            <p>
                              World dates: {fact.valid_from ?? 'Unknown start'}{' '}
                              to {fact.valid_to ?? 'Unknown end'} (end
                              exclusive). Recorded{' '}
                              {new Date(
                                fact.recorded_at / 1000,
                              ).toLocaleString()}
                              .
                            </p>
                            {fact.evidence.map((entry) => (
                              <div key={entry.source_id}>
                                {entry.quote && (
                                  <blockquote>{entry.quote}</blockquote>
                                )}
                                {source(
                                  entry.source_id,
                                  'View statement evidence',
                                )}
                              </div>
                            ))}
                          </li>
                        ))}
                    </ul>
                    <h5>Photo gallery links</h5>
                    {!result.sections.photos?.some(
                      (row) => row.asset_id === record.id,
                    ) && <p>No photo links recorded.</p>}
                    <ul>
                      {result.sections.photos
                        ?.filter((row) => row.asset_id === record.id)
                        .map((row) => (
                          <li key={row.link_id}>
                            {row.filename} · {row.purpose} ·{' '}
                            {row.deleted
                              ? 'Original deleted; historical link retained'
                              : 'Private original retained'}
                            {row.source_id &&
                              source(row.source_id, 'View photo transcription')}
                          </li>
                        ))}
                    </ul>
                    <h5>Current discovery associations</h5>
                    {!result.sections.associations?.some(
                      (row) => row.asset_id === record.id,
                    ) && <p>No current discovery associations.</p>}
                    <ul>
                      {result.sections.associations
                        ?.filter((row) => row.asset_id === record.id)
                        .map((row) => (
                          <li key={row.decision_id}>
                            {row.name} · unit {row.unit} of {row.quantity}.
                            Manufacturer: {row.manufacturer ?? 'Unknown'};
                            serial: {row.serial ?? 'Unknown'}.
                            {source(row.source_id, 'View discovery evidence')}
                          </li>
                        ))}
                    </ul>
                    <h5>Receipt line claims</h5>
                    {!result.sections.receipt_lines?.some(
                      (row) => row.asset_id === record.id,
                    ) && <p>No linked receipt line claims.</p>}
                    <p>
                      Amounts describe the whole receipt line, across all its
                      units. Repeated evidence is not another purchase total.
                    </p>
                    <ul>
                      {result.sections.receipt_lines
                        ?.filter((row) => row.asset_id === record.id)
                        .map((row) => (
                          <li key={row.key}>
                            {row.name} · unit {row.unit} of {row.quantity}.
                            Whole line:{' '}
                            {row.claim?.line_total
                              ? `${row.claim.currency} ${row.claim.line_total}`
                              : 'Unknown'}
                            . Purchase date:{' '}
                            {row.claim?.purchase_date ?? 'Unknown'}.
                            {!row.source_current && (
                              <p>Historical: corrected or deleted source.</p>
                            )}
                            {source(row.source_id, 'View receipt evidence')}
                          </li>
                        ))}
                    </ul>
                    {result.sections.maintenance?.some(
                      (row) => row.asset_id === record.id,
                    ) && (
                      <>
                        <h5>Stated maintenance tasks</h5>
                        <ul>
                          {result.sections.maintenance
                            .filter((row) => row.asset_id === record.id)
                            .map((row) => (
                              <li key={row.id}>
                                {row.title} · {row.state}. Due:{' '}
                                {row.due_on ?? 'Unknown'} · {row.timezone}.
                                Completion date: {row.completed_on ?? 'Unknown'}
                                .
                                {source(
                                  row.source_id,
                                  'View maintenance statement',
                                )}
                              </li>
                            ))}
                        </ul>
                      </>
                    )}
                  </article>
                ))}
              </div>
              <h4>Related purchase evidence</h4>
              {!result.sections.purchase_evidence?.length && (
                <p>No related cross-source purchase evidence.</p>
              )}
              <p>
                Each source association appears once here. Order/receipt totals
                and payments remain separate source claims; they are not added
                together or allocated to individual items.
              </p>
              <ul>
                {result.sections.purchase_evidence?.map((row) => (
                  <li key={row.id}>
                    {row.role} · {purchaseLabel(row.purchase_id)} ·{' '}
                    {row.amount_minor === null
                      ? 'Amount unknown'
                      : amount(row.amount_minor, row.currency)}{' '}
                    · event {row.occurred_on ?? 'date unknown'}.
                    {!row.source_current && (
                      <p>Historical: corrected or deleted source.</p>
                    )}
                    <blockquote>{row.quote}</blockquote>
                    {source(row.source_id, 'View purchase evidence')}
                  </li>
                ))}
              </ul>
              <p>
                This is a read snapshot. Refresh the comparison after any
                changes; it does not authorize a later merge.
              </p>
            </>
          )}
        </>
      )}
    </section>
  )
}
