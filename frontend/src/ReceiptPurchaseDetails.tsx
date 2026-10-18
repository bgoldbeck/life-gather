import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ChatRequestError } from './chatRequest'
type Revision = {
  id: string
  revision: number
  line_total: string | null
  total_minor: number | null
  currency: string | null
  purchase_date: string | null
  money_quote: string | null
  date_quote: string | null
  reason: string
  recorded_at: number
}
type Page = {
  current_head: string | null
  current: Revision | null
  can_edit: boolean
  items: Revision[]
  next_revision: number | null
  quantity: number
}
export function ReceiptPurchaseDetails({
  id,
  index,
  csrfToken,
}: {
  id: string
  index: number
  csrfToken: string
}) {
  const [page, setPage] = useState<Page | null>(null)
  const [total, setTotal] = useState('')
  const [moneyQuote, setMoneyQuote] = useState('')
  const [date, setDate] = useState('')
  const [dateQuote, setDateQuote] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [retry, setRetry] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const pending = useRef<Record<string, unknown> | null>(null)
  const request = useCallback(
    async (path: string, body: unknown, signal?: AbortSignal) => {
      const response = await fetch('/api/receipts/details/' + path, {
        method: 'POST',
        cache: 'no-store',
        credentials: 'same-origin',
        signal,
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify(body),
      })
      if (!response.ok)
        throw new ChatRequestError(
          'Unable to save purchase details. Use exact labeled source passages; reload if this note or its details changed.',
          response.status,
        )
      return response.json()
    },
    [csrfToken],
  )
  const apply = useCallback((row: Page) => {
    setPage(row)
    setTotal(row.current?.line_total ?? '')
    setMoneyQuote(row.current?.money_quote ?? '')
    setDate(row.current?.purchase_date ?? '')
    setDateQuote(row.current?.date_quote ?? '')
    setReason('')
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    void request('read', { receipt_id: id, index }, controller.signal)
      .then((row) => {
        if (!controller.signal.aborted) apply(row)
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError('Unable to load purchase details. Reload to try again.')
      })
    return () => controller.abort()
  }, [id, index, request, apply])
  async function load(older = false) {
    setBusy(true)
    setError('')
    try {
      const row: Page = await request('read', {
        receipt_id: id,
        index,
        before_revision: older ? (page?.next_revision ?? 0) : 0,
      })
      if (older)
        setPage((current) =>
          current
            ? {
                ...current,
                items: [...current.items, ...row.items],
                next_revision: row.next_revision,
              }
            : row,
        )
      else apply(row)
    } catch {
      setError('Unable to load purchase details. Try reloading.')
    } finally {
      setBusy(false)
    }
  }
  async function save() {
    if (busy) return
    setBusy(true)
    setError('')
    setNotice('')
    const body = pending.current ?? {
      receipt_id: id,
      index,
      expected_head: page?.current_head ?? null,
      request_id: crypto.randomUUID(),
      line_total: total || null,
      money_quote: moneyQuote || null,
      purchase_date: date || null,
      date_quote: dateQuote || null,
      reason,
    }
    pending.current = body
    try {
      const row: Revision = await request('save', body)
      pending.current = null
      setRetry(false)
      apply({
        current_head: row.id,
        current: row,
        can_edit: page?.can_edit ?? false,
        quantity: page?.quantity ?? 0,
        items: [
          row,
          ...(page?.items ?? []).filter((item) => item.id !== row.id),
        ],
        next_revision: page?.next_revision ?? null,
      })
      setNotice(
        'Purchase details saved with source evidence. Earlier revisions are preserved.',
      )
    } catch (caught) {
      if (caught instanceof ChatRequestError && caught.status < 500) {
        pending.current = null
        setRetry(false)
      } else setRetry(true)
      setError((caught as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const locked = busy || retry || !page?.can_edit
  return (
    <section
      className="receipt-purchase-details"
      aria-label={`Purchase details for item ${index + 1}`}
    >
      <h3>Purchase details for item {index + 1}</h3>
      <p>
        Optional source claims, not verified accounting. The line total covers
        all {page?.quantity ?? 'selected'} units together; it is never
        multiplied by quantity. Only explicit USD totals and YYYY-MM-DD purchase
        dates are supported. Leave unknown values blank.
      </p>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <Button
        variant="outline"
        disabled={busy || retry}
        onClick={() => void load()}
      >
        Reload purchase details
      </Button>
      {page && !page.can_edit && (
        <p>
          The original source changed or was deleted. These historical details
          remain readable; new details require a current receipt source.
        </p>
      )}
      {page && (
        <>
          <fieldset disabled={locked}>
            <label>
              USD line total
              <input
                aria-label={`USD line total ${index + 1}`}
                value={total}
                inputMode="decimal"
                maxLength={12}
                placeholder="49.90"
                onChange={(e) => setTotal(e.target.value)}
              />
            </label>
            <label>
              Exact item and line-total passage
              <textarea
                aria-label={`Line-total passage ${index + 1}`}
                value={moneyQuote}
                maxLength={500}
                placeholder="Copy the reviewed item quote and Line total: USD 49.90"
                onChange={(e) => setMoneyQuote(e.target.value)}
              />
            </label>
            <label>
              Purchase date
              <input
                aria-label={`Purchase date ${index + 1}`}
                value={date}
                maxLength={10}
                placeholder="YYYY-MM-DD"
                onChange={(e) => setDate(e.target.value)}
              />
            </label>
            <label>
              Exact purchase-date passage
              <input
                aria-label={`Purchase-date passage ${index + 1}`}
                value={dateQuote}
                maxLength={200}
                placeholder="Purchase date: 2026-10-18"
                onChange={(e) => setDateQuote(e.target.value)}
              />
            </label>
            <label>
              Reason for this revision
              <input
                aria-label={`Revision reason ${index + 1}`}
                value={reason}
                maxLength={300}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>
          </fieldset>
          <Button
            disabled={busy || !page.can_edit || (!retry && !reason.trim())}
            onClick={() => void save()}
          >
            {retry ? 'Retry same purchase details' : 'Save purchase details'}
          </Button>
          {retry && (
            <p>
              The response was lost. Fields are frozen so you can safely retry
              the same revision.
            </p>
          )}
          <h4>Recorded history</h4>
          {!page.items.length && <p>No purchase total or date recorded.</p>}
          <ol>
            {page.items.map((item) => (
              <li key={item.id}>
                <p>
                  Revision {item.revision} ·{' '}
                  {new Date(item.recorded_at / 1000).toLocaleString()}
                </p>
                <p>
                  Line total:{' '}
                  {item.line_total === null
                    ? 'unknown'
                    : `${item.currency} ${item.line_total}`}{' '}
                  · Purchase date: {item.purchase_date ?? 'unknown'}
                </p>
                {item.money_quote && (
                  <blockquote>{item.money_quote}</blockquote>
                )}
                {item.date_quote && <blockquote>{item.date_quote}</blockquote>}
                <p>{item.reason}</p>
              </li>
            ))}
          </ol>
          {page.next_revision && (
            <Button
              variant="outline"
              disabled={busy || retry}
              onClick={() => void load(true)}
            >
              Earlier purchase revisions
            </Button>
          )}
        </>
      )}
    </section>
  )
}
