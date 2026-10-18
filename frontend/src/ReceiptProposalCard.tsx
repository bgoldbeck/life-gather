import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ChatRequestError } from './chatRequest'
import { ReceiptPurchaseDetails } from './ReceiptPurchaseDetails'
import { CandidateComparison } from './CandidateComparison'

type Fields = {
  name: string
  manufacturer: string | null
  model: string | null
  serial: string | null
  kind: 'purchase' | 'possession' | 'mention'
  quote: string
  quantity: number
  quantity_quote: string | null
}
type Receipt = {
  id: string
  source_id: string
  current_source_id: string
  stale: boolean
  state: string
  explanation: string
  items: Fields[]
  review_actions?: Choice[] | null
  result: { lines?: { asset_ids: string[]; automatic_outcome?: string }[] }
  automatic_outcome?: 'review'
  automatic_checks?: (Check & {
    index: number
    reason: string
    outcome: string
  })[]
}
type Check = {
  check: string
  candidates: { id: string; name: string }[]
  reliable_ids: string[]
}
type Choice = { action: 'skip' | 'new' | 'link' | 'auto'; asset_ids: string[] }

export function ReceiptProposalCard({
  id,
  csrfToken,
  onOpen,
  onReviewed,
}: {
  id: string
  csrfToken: string
  onOpen: (id: string) => Promise<void>
  onReviewed?: () => Promise<void>
}) {
  const [receipt, setReceipt] = useState<Receipt | null>(null)
  const [fields, setFields] = useState<Fields[]>([])
  const [choices, setChoices] = useState<Choice[]>([])
  const [checks, setChecks] = useState<(Check | null)[]>([])
  const [ownership, setOwnership] = useState('')
  const [busy, setBusy] = useState(false)
  const [retry, setRetry] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef<Record<string, unknown> | null>(null)
  const request = useCallback(
    async (path: string, init?: RequestInit) => {
      const response = await fetch('/api/receipts' + path, {
        ...init,
        cache: 'no-store',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
      })
      if (!response.ok)
        throw new ChatRequestError(
          'Unable to complete receipt review. Check the quotes and quantities, then reload if the source or duplicates changed.',
          response.status,
        )
      return response.json()
    },
    [csrfToken],
  )
  const apply = useCallback((row: Receipt) => {
    setReceipt(row)
    setFields(row.items)
    setChoices(
      row.review_actions ??
        row.items.map(() => ({ action: 'skip', asset_ids: [] })),
    )
    setChecks(row.items.map(() => null))
    setOwnership('')
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    void request('/' + id, { signal: controller.signal })
      .then((row) => {
        if (!controller.signal.aborted) apply(row)
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError('Unable to load the receipt. Reopen this review to retry.')
      })
    return () => controller.abort()
  }, [request, id, apply])
  function edit(index: number, key: keyof Fields, value: string) {
    setFields((current) =>
      current.map((f, i) =>
        i === index
          ? {
              ...f,
              [key]:
                key === 'quantity'
                  ? Number(value)
                  : [
                        'manufacturer',
                        'model',
                        'serial',
                        'quantity_quote',
                      ].includes(key)
                    ? value || null
                    : value,
            }
          : f,
      ),
    )
    setChecks((current) => current.map((c, i) => (i === index ? null : c)))
    setReceipt(
      (current) =>
        current && {
          ...current,
          automatic_checks: current.automatic_checks?.filter(
            (check) => check.index !== index,
          ),
        },
    )
    setError('')
    if (key === 'quantity')
      setChoices((current) =>
        current.map((c, i) => (i === index ? { ...c, asset_ids: [] } : c)),
      )
  }
  async function check(index: number) {
    setBusy(true)
    setError('')
    try {
      const result: Check = await request('/preview', {
        method: 'POST',
        body: JSON.stringify({ receipt_id: id, index, fields: fields[index] }),
      })
      setChecks((current) => current.map((c, i) => (i === index ? result : c)))
      if (result.reliable_ids.length)
        setChoices((current) =>
          current.map((c, i) =>
            i === index && c.action === 'new'
              ? { action: 'link', asset_ids: [] }
              : c,
          ),
        )
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setBusy(false)
    }
  }
  async function decide(reject = false) {
    if (busy) return
    setBusy(true)
    setError('')
    const body = pending.current ?? {
      receipt_id: id,
      request_id: crypto.randomUUID(),
      reject,
      choices: reject
        ? []
        : choices.map((choice, index) => ({
            index,
            fields: fields[index],
            ...choice,
            check: checks[index]?.check ?? '',
          })),
    }
    pending.current = body
    try {
      const row = await request('/review', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      pending.current = null
      setRetry(false)
      if (row.state === 'proposed' && row.automatic_outcome === 'review') {
        setReceipt(row)
        setChecks((current) =>
          current.map(
            (value, index) =>
              row.automatic_checks?.find(
                (check: Check & { index: number }) => check.index === index,
              ) ?? value,
          ),
        )
        setError(
          'Nothing was recorded. Some identities need your decision. Compare the evidence and choose same or different items for those lines.',
        )
        return
      }
      apply(row)
      try {
        await onReviewed?.()
      } catch {
        setError('Receipt saved. Refresh the queue to see updated work.')
      }
    } catch (caught) {
      if (caught instanceof ChatRequestError && caught.status < 500) {
        pending.current = null
        setRetry(false)
        setChecks((current) => current.map(() => null))
      } else setRetry(true)
      setError((caught as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const selected = choices
    .map((c, i) => (c.action === 'skip' ? -1 : i))
    .filter((i) => i >= 0)
  const total = selected.reduce((n, i) => n + fields[i].quantity, 0)
  const targets = selected.flatMap((i) => choices[i].asset_ids)
  const valid =
    !!ownership &&
    selected.length > 0 &&
    total <= 20 &&
    new Set(targets).size === targets.length &&
    selected.every(
      (i) =>
        (choices[i].action === 'auto' || checks[i]) &&
        Number.isInteger(fields[i].quantity) &&
        fields[i].quantity > 0 &&
        fields[i].quantity <= 20 &&
        (choices[i].action !== 'link' ||
          (choices[i].asset_ids.filter(Boolean).length === fields[i].quantity &&
            new Set(choices[i].asset_ids).size === fields[i].quantity)),
    )
  const editable = receipt?.state === 'proposed' && !receipt.stale
  return (
    <section
      className="asset-proposal receipt-proposal"
      aria-label="Multi-item receipt review"
    >
      <h2>Receipt review</h2>
      {!receipt && !error && <p role="status">Loading receipt…</p>}
      {error && <p role="alert">{error}</p>}
      {receipt && (
        <>
          <p>{receipt.explanation}</p>
          <p>
            Check each exact quote and quantity against its original.
            Suggestions are unverified. Prices and dates are not inferred. After
            confirming purchased items, you can record optional source-backed
            purchase details.
          </p>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => void onOpen(receipt.source_id)}
          >
            View receipt source
          </Button>
          {receipt.stale && (
            <p>
              A newer source correction exists. Reject this draft and extract
              from the current note.
            </p>
          )}
          {receipt.stale && (
            <Button
              variant="outline"
              onClick={() => void onOpen(receipt.current_source_id)}
            >
              View current receipt note
            </Button>
          )}
          {receipt.state === 'accepted' && (
            <p role="status">
              Receipt confirmed.{' '}
              {receipt.result.lines?.reduce(
                (n, line) => n + line.asset_ids.length,
                0,
              ) ?? 0}{' '}
              physical units linked with original source evidence. Ownership is
              inferred.
            </p>
          )}
          {receipt.state === 'accepted' &&
            receipt.result.lines?.some((line) => line.automatic_outcome) && (
              <p>
                Clear identities were recorded automatically from your reviewed
                fields. This does not independently verify ownership.
              </p>
            )}
          {receipt.state === 'rejected' && (
            <p role="status">
              Receipt rejected. Original evidence is preserved.
            </p>
          )}
          {receipt.state === 'no_items' && (
            <p>
              No clear item lines were extracted. Nothing was added to
              inventory.
            </p>
          )}
          {editable && (
            <label>
              Your relationship to the selected items
              <select
                value={ownership}
                disabled={busy || retry}
                onChange={(e) => {
                  const value = e.target.value as Fields['kind'] | ''
                  setOwnership(value)
                  setFields((current) =>
                    current.map((f) => ({ ...f, kind: value || 'mention' })),
                  )
                  setChecks((current) => current.map(() => null))
                }}
              >
                <option value="">Choose your statement</option>
                <option value="purchase">I purchased these items</option>
                <option value="possession">I possess these items</option>
              </select>
            </label>
          )}
          {fields.map((item, index) => (
            <fieldset
              key={index}
              disabled={busy || retry || !editable}
              className="receipt-line"
            >
              <legend>
                Item {index + 1}: {item.name}
              </legend>
              <label>
                Item name {index + 1}
                <input
                  value={item.name}
                  maxLength={200}
                  onChange={(e) => edit(index, 'name', e.target.value)}
                />
              </label>
              {(['manufacturer', 'model', 'serial'] as const).map((key) => (
                <label key={key}>
                  {key === 'serial'
                    ? 'Serial'
                    : key === 'model'
                      ? 'Model'
                      : 'Manufacturer'}{' '}
                  {index + 1}
                  <input
                    value={item[key] ?? ''}
                    maxLength={100}
                    onChange={(e) => edit(index, key, e.target.value)}
                  />
                </label>
              ))}
              <label>
                Quantity {index + 1}
                <input
                  type="number"
                  min={1}
                  max={20}
                  step={1}
                  value={item.quantity}
                  onChange={(e) => edit(index, 'quantity', e.target.value)}
                />
              </label>
              <label>
                Exact item quote {index + 1}
                <textarea
                  value={item.quote}
                  maxLength={1000}
                  onChange={(e) => edit(index, 'quote', e.target.value)}
                />
              </label>
              <label>
                Exact quantity passage {index + 1}
                <input
                  value={item.quantity_quote ?? ''}
                  maxLength={200}
                  onChange={(e) =>
                    edit(index, 'quantity_quote', e.target.value)
                  }
                />
              </label>
              <p>
                Multiple units need “Qty 2”, “quantity: 2”, “count 2” or “2
                units/pcs/pieces” in this item's quote. An unstated single unit
                still requires your review.
              </p>
              <label>
                Record item {index + 1}
                <select
                  value={choices[index]?.action ?? 'skip'}
                  onChange={(e) =>
                    setChoices((current) =>
                      current.map((c, i) =>
                        i === index
                          ? {
                              action: e.target.value as Choice['action'],
                              asset_ids: [],
                            }
                          : c,
                      ),
                    )
                  }
                >
                  <option value="skip">Exclude this line</option>
                  <option value="auto">Record if identity is clear</option>
                  <option
                    value="new"
                    disabled={!!checks[index]?.reliable_ids.length}
                  >
                    Different item(s) — create new records
                  </option>
                  <option value="link">
                    Same item(s) — choose existing records
                  </option>
                </select>
              </label>
              {choices[index]?.action === 'auto' && (
                <p>
                  Uses these reviewed fields and your relationship statement.
                  Clear new items are added; reliable active identities enrich
                  existing records. If any selected automatic identity is
                  ambiguous, nothing is recorded. Similar names never merge
                  physical items.
                </p>
              )}
              {receipt.automatic_checks?.find((check) => check.index === index)
                ?.outcome === 'review' && (
                <p role="status">
                  Needs an explicit identity decision:{' '}
                  {
                    receipt.automatic_checks.find(
                      (check) => check.index === index,
                    )?.reason
                  }
                </p>
              )}
              {editable && choices[index]?.action !== 'skip' && (
                <Button
                  variant="outline"
                  disabled={!ownership}
                  onClick={() => void check(index)}
                >
                  Check item {index + 1} and duplicates
                </Button>
              )}
              {checks[index] && (
                <p role="status">
                  Item {index + 1} checked. {checks[index]!.candidates.length}{' '}
                  possible match(es). Names alone do not prove identity.
                </p>
              )}
              {checks[index] && (
                <CandidateComparison
                  key={JSON.stringify(checks[index]!.candidates)}
                  candidates={checks[index]!.candidates}
                  onOpen={onOpen}
                  disabled={busy || retry}
                  label={`Compare possible items for receipt line ${index + 1}`}
                />
              )}
              {checks[index]?.reliable_ids.length ? (
                <p>
                  An identifier matches an existing item. Choose the existing
                  physical record.
                </p>
              ) : null}
              {choices[index]?.action === 'link' &&
                checks[index] &&
                Array.from(
                  { length: Math.min(20, Math.max(0, item.quantity)) },
                  (_, unit) => (
                    <label key={unit}>
                      Existing record for item {index + 1}, unit {unit + 1}
                      <select
                        value={choices[index].asset_ids[unit] ?? ''}
                        onChange={(e) =>
                          setChoices((current) =>
                            current.map((c, i) =>
                              i === index
                                ? {
                                    ...c,
                                    asset_ids: Array.from(
                                      { length: item.quantity },
                                      (_, u) =>
                                        u === unit
                                          ? e.target.value
                                          : (c.asset_ids[u] ?? ''),
                                    ),
                                  }
                                : c,
                            ),
                          )
                        }
                      >
                        <option value="">Choose a distinct record</option>
                        {checks[index]!.candidates.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name} · {c.id.slice(0, 8)}
                          </option>
                        ))}
                      </select>
                    </label>
                  ),
                )}
            </fieldset>
          ))}
          {receipt.state === 'accepted' &&
            fields.map((item, index) =>
              item.kind === 'purchase' && choices[index]?.action !== 'skip' ? (
                <ReceiptPurchaseDetails
                  key={index}
                  id={id}
                  index={index}
                  csrfToken={csrfToken}
                />
              ) : null,
            )}
          {editable && (
            <p>
              {selected.length} selected line(s), {total} physical unit(s).
              Review all selected fields. Manual identity choices require a
              duplicate check; automatic choices are checked when saving. All
              selected lines save together.
            </p>
          )}
          {editable && (
            <Button
              disabled={busy || (!retry && !valid)}
              onClick={() => void decide()}
            >
              {retry
                ? 'Retry same receipt review'
                : 'Confirm selected receipt items'}
            </Button>
          )}
          {receipt.state === 'proposed' && (
            <Button
              variant="outline"
              disabled={busy || retry}
              onClick={() => void decide(true)}
            >
              Reject receipt proposal
            </Button>
          )}
        </>
      )}
    </section>
  )
}
